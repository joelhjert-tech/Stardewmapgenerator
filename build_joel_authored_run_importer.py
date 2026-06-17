#!/usr/bin/env python3
"""
build_joel_authored_run_importer.py  (READ-ONLY w.r.t. sources)

Content-based importer for Joel-authored mine/dungeon pattern .tmx files. Produces:
  Task 1  source_inventory.json + report
  Task 2  normalized/tile_id_structural_role_map.json + report   (classify by tile-id + geometry)
  Task 3  normalized/normalized_authored_patterns.json + report  (layer normalization, content-based)
  Task 4  joel_authored_runs_v1.json + schema                    (one complete run per pattern)

Classifies every tile by its STRUCTURAL ROLE (geometry + sheet position + tilesheet Type
property + corpus role model), never by layer name alone. Source files are never modified.
"""
from __future__ import annotations
import json, re, sys, base64, zlib, struct, collections
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PL = ROOT / "pattern_learning"
CUSTOM = PL / "Joel_custompatterns"
OUT = PL / "joel_authored_runs_v1"
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT))
import mbb_common as C  # noqa: E402

FLIP = 0x1FFFFFFF
VOID = {77, 135}
SHADOW = {214, 215}
SHEET_COLS = 16
TS = datetime.now(timezone.utc).isoformat()


def parse_tmx(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    mm = re.search(r'<map[^>]*\bwidth="(\d+)"\s+height="(\d+)"', txt)
    w, h = int(mm.group(1)), int(mm.group(2))
    layers = {}
    for lm in re.finditer(r'<layer[^>]*\bname="([^"]+)"[^>]*>\s*<data([^>]*)>\s*(.*?)\s*</data>', txt, re.S):
        name, attrs, body = lm.group(1), lm.group(2), lm.group(3)
        if 'encoding="base64"' in attrs:
            raw = base64.b64decode(body.strip())
            if "zlib" in attrs or "gzip" in attrs:
                raw = zlib.decompress(raw)
            nums = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
        else:
            nums = [int(v) for v in re.findall(r'-?\d+', body)]
        grid = {}
        for i, gid in enumerate(nums):
            if gid:
                grid[(i % w, i // w)] = (gid & FLIP) - 1
        layers[name] = grid
    # tilesheet per-tile Type properties (Dirt/Stone/Wood)
    types = {}
    for tm in re.finditer(r'<tile id="(\d+)">\s*<properties>(.*?)</properties>', txt, re.S):
        tid = int(tm.group(1))
        pm = re.search(r'name="Type"\s+value="([^"]+)"', tm.group(2))
        if pm:
            types[tid] = pm.group(1)
    tilesheets = re.findall(r'<image source="([^"]+)"', txt)
    return {"w": w, "h": h, "layers": layers, "types": types, "tilesheets": tilesheets}


# ---------- discovery (Task 1) ----------
def discover():
    entries = []
    for batch_dir, batch in [(CUSTOM, "batch_1"), (CUSTOM / "Patter_2", "batch_2")]:
        if not batch_dir.exists():
            continue
        for f in sorted(batch_dir.glob("*.tmx")):
            is_ref = bool(re.search(r'refr', f.name, re.I))
            entries.append({"path": str(f.relative_to(ROOT)), "name": f.name, "batch": batch,
                            "sourceType": "authored_reference_map" if is_ref else "authored_pattern"})
    return entries


# ---------- tile-id structural role map (Task 2) ----------
def build_reference_geometry(model):
    """From the two reference maps (proper Back/Buildings/Front convention), accumulate each
    wall tile's floor-neighbour direction histogram -> dominant boundary geometry."""
    walls = set(model["buildingsWallIds"]); floors = set(model["backFloorIds"])
    dir_hist = collections.defaultdict(collections.Counter)
    refs = [CUSTOM / "refrencemapmines1.tmx", CUSTOM / "Patter_2" / "refrensmap2.tmx"]
    for rp in refs:
        if not rp.exists():
            continue
        d = parse_tmx(rp)
        back = d["layers"].get("Back", {}); bld = d["layers"].get("Buildings", {})
        def is_floor(x, y):
            t = back.get((x, y))
            return t is not None and t in floors and (x, y) not in bld
        for (x, y), t in bld.items():
            if t in VOID:
                continue
            for d8, (dx, dy) in {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0),
                                 "NE": (1, -1), "SE": (1, 1), "SW": (-1, 1), "NW": (-1, -1)}.items():
                if is_floor(x + dx, y + dy):
                    dir_hist[t][d8] += 1
    return dir_hist


def wall_subrole(tid, dir_hist):
    h = dir_hist.get(tid)
    cap = tid < 48  # top rows of the mine sheet = ceiling / top-wall cap art
    if not h:
        return "top_wall_cap" if cap else "wall_body"
    card = {d: h[d] for d in ("N", "E", "S", "W") if h[d]}
    if not card:
        return "top_wall_cap" if cap else "wall_body"
    dom = max(card, key=card.get)
    multi = sum(1 for d in card if card[d] >= max(card.values()) * 0.5)
    if multi >= 2:
        return "corner"
    return {"S": "lower_wall_face", "N": "top_wall_cap" if cap else "top_wall_body",
            "E": "left_wall_edge", "W": "right_wall_edge"}[dom]


def build_tile_role_map(model, pattern_files):
    walls = set(model["buildingsWallIds"]); floors = set(model["backFloorIds"])
    objs = set(model["buildingsObjectIds"]); ladders = set(model["ladderIds"])
    dir_hist = build_reference_geometry(model)
    # gather Type props + which patterns/refs use each id
    types = {}; used_in = collections.defaultdict(set); ref_use = collections.defaultdict(set)
    all_files = pattern_files + [{"path": str((CUSTOM / "refrencemapmines1.tmx").relative_to(ROOT)), "name": "refrencemapmines1.tmx", "sourceType": "authored_reference_map"},
                                 {"path": str((CUSTOM / "Patter_2" / "refrensmap2.tmx").relative_to(ROOT)), "name": "refrensmap2.tmx", "sourceType": "authored_reference_map"}]
    for e in all_files:
        d = parse_tmx(ROOT / e["path"])
        types.update(d["types"])
        for grid in d["layers"].values():
            for t in grid.values():
                if e["sourceType"] == "authored_reference_map":
                    ref_use[t].add(e["name"])
                else:
                    used_in[t].add(e["name"])
    all_ids = set(types) | set(used_in) | set(ref_use) | walls | floors | objs | ladders | SHADOW | VOID

    def role_for(tid):
        if tid in VOID:
            return "deep_void", "Back", 95
        if tid in ladders:
            return "ladder", "Buildings", 90
        if types.get(tid) == "Wood":
            return "wood_support", "Buildings", 80
        if tid in SHADOW:
            return "shadow", "Front", 90
        if tid in objs:
            return "decoration", "Front", 60
        if tid in walls:
            return wall_subrole(tid, dir_hist), "Buildings", 80 if dir_hist.get(tid) else 60
        if tid in floors or types.get(tid) == "Dirt":
            return "floor", "Back", 85
        if types.get(tid) == "Stone":
            # stone not in wall set -> floor-grade stone terrain
            return "floor_variation", "Back", 65
        return "unknown", "Back", 30

    role_map = {}
    for tid in sorted(all_ids):
        role, layer, conf = role_for(tid)
        allowed = {"floor": ["Back"], "floor_variation": ["Back"], "deep_void": ["Back", "Buildings"],
                   "shadow": ["Front"], "decoration": ["Front", "Buildings"], "ladder": ["Buildings", "Front"],
                   "wood_support": ["Buildings"]}.get(role, ["Buildings"])
        paired = {"lower_wall_face": ["shadow", "floor"], "top_wall_cap": ["top_wall_body"],
                  "top_wall_body": ["top_wall_cap", "lower_wall_face"], "shadow": ["lower_wall_face", "top_wall_body"],
                  "ladder": ["floor"], "corner": ["lower_wall_face", "left_wall_edge", "right_wall_edge"]}.get(role, [])
        role_map[str(tid)] = {
            "localTileId": tid, "structuralRole": role, "preferredLayer": layer,
            "allowedLayers": allowed, "disallowedLayers": [L for L in ("Back", "Buildings", "Front") if L not in allowed and L != layer],
            "pairedRoles": paired, "sheetRowCol": [tid // SHEET_COLS, tid % SHEET_COLS],
            "typeProperty": types.get(tid), "floorNeighborDirs": dict(dir_hist.get(tid, {})),
            "examplePatterns": sorted(used_in.get(tid, []))[:4],
            "exampleReferenceMaps": sorted(ref_use.get(tid, [])),
            "confidence": conf,
            "notes": ("top rows of mine sheet = ceiling/top-wall cap art" if (role == "top_wall_cap" and tid < 48) else ""),
        }
    return role_map, dir_hist


# ---------- normalization + runs (Tasks 3 & 4) ----------
def cell_role(tid, role_map):
    return role_map.get(str(tid), {}).get("structuralRole", "unknown")


def canonical_layer(role):
    if role in ("floor", "floor_variation", "deep_void"):
        return "Back"
    if role in ("shadow",):
        return "Front"
    return "Buildings"  # all wall/corner/top/lower/edge/ladder/decoration/wood structural roles


WALL_ROLES = {"top_wall_cap", "top_wall_body", "lower_wall_face", "left_wall_edge", "right_wall_edge",
              "corner", "wall_body", "angled_wall", "diagonal_transition"}
OPENING_ROLES = {"ladder", "shaft", "entrance"}
DECO_ROLES = {"decoration", "wood_support", "vine_plant", "torch_light"}


def infer_run_type_orientation(name):
    n = name.lower()
    o = "unknown"
    if "topwall" in n or "toppwall" in n or "topp" in n:
        base = "top_wall_run"; o = "north/top"
        if "flowing" in n or "design" in n:
            base = "top_wall_flowing_design"
        if "hardcorner" in n:
            base = "top_wall_hard_corner_to_side"
        if "softbend" in n or "slightbend" in n or "softcurve" in n:
            base = "top_wall_soft_bend"
    elif "bottomwall" in n or "buttomwall" in n or "lower" in n:
        base = "lower_face_run"; o = "south/lower"
        if "bothsides" in n:
            base = "lower_face_both_sides_curve"
        elif "softcurve" in n or "softbend" in n or "slightdown" in n:
            base = "lower_face_soft_curve"
    elif "entrenceladder" in n or "ladder" in n and "from" not in n:
        base = "ladder_entrance"; o = "north/top"
    elif "leftside" in n or "leftwall" in n:
        base = "left_wall_run"; o = "west/left"
    elif "rightside" in n or "rightwall" in n:
        base = "right_wall_run"; o = "east/right"
    else:
        base = "wall_body_run"
    if "hardcorner" in n:
        base = "hard_corner"
    elif "softcorner" in n or "softbend" in n or "slightbend" in n:
        base = "soft_corner" if "corner" in n else base
    elif ("corner" in n or "bend" in n) and base in ("left_wall_run", "right_wall_run", "wall_body_run"):
        base = "soft_corner" if ("soft" in n or "slight" in n) else "inner_corner"
    return base, o


def extract_run(entry, role_map):
    path = ROOT / entry["path"]
    d = parse_tmx(path)
    w, h = d["w"], d["h"]
    # merge all layers, classify each cell by tile-id role (wall beats floor beats void)
    rank = {"deep_void": 0, "floor": 1, "floor_variation": 1, "unknown": 1, "shadow": 2,
            "decoration": 3, "wood_support": 3, "ladder": 4,
            "wall_body": 5, "top_wall_cap": 5, "top_wall_body": 5, "lower_wall_face": 5,
            "left_wall_edge": 5, "right_wall_edge": 5, "corner": 6, "angled_wall": 5, "diagonal_transition": 5}
    cell_tid = {}; cell_rl = {}; original = []; mismatches = []
    for lname, grid in d["layers"].items():
        for (x, y), t in grid.items():
            rl = cell_role(t, role_map)
            original.append({"x": x, "y": y, "layer": lname, "tileId": t, "role": rl})
            canon = canonical_layer(rl)
            if canon != lname and rl not in ("unknown",):
                mismatches.append({"x": x, "y": y, "tileId": t, "role": rl,
                                   "originalLayer": lname, "normalizedLayer": canon,
                                   "reason": f"tileId role {rl} belongs on {canon} (content-based)"})
            if rank.get(rl, 1) >= rank.get(cell_rl.get((x, y), "deep_void"), 0):
                cell_rl[(x, y)] = rl; cell_tid[(x, y)] = t
    cells = sorted(cell_rl)
    if not cells:
        return None
    xs = [x for x, y in cells]; ys = [y for x, y in cells]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    # normalized layer stack (anchored at bbox top-left)
    norm_stack, masks = [], {"floorMask": [], "wallMask": [], "voidMask": [], "shadowMask": [],
                             "openingMask": [], "decorationMask": [], "collisionMask": []}
    ids_by_role = collections.defaultdict(set); ids_by_layer = collections.defaultdict(set)
    for (x, y) in cells:
        t = cell_tid[(x, y)]; rl = cell_rl[(x, y)]; dx, dy = x - x0, y - y0
        layer = canonical_layer(rl)
        norm_stack.append({"dx": dx, "dy": dy, "role": rl, "layer": layer, "tileId": t})
        ids_by_role[rl].add(t); ids_by_layer[layer].add(t)
        if rl in ("floor", "floor_variation"):
            masks["floorMask"].append([dx, dy])
        elif rl in WALL_ROLES:
            masks["wallMask"].append([dx, dy]); masks["collisionMask"].append([dx, dy])
        elif rl == "shadow":
            masks["shadowMask"].append([dx, dy])
        elif rl in OPENING_ROLES:
            masks["openingMask"].append([dx, dy])
        elif rl in DECO_ROLES:
            masks["decorationMask"].append([dx, dy])
        else:
            masks["voidMask"].append([dx, dy])
    run_type, orientation = infer_run_type_orientation(entry["name"])
    # generator placement role + anchor: a wall cell adjacent to floor (contact edge)
    floorset = {(c["dx"], c["dy"]) for c in norm_stack if c["role"] in ("floor", "floor_variation")}
    wallset = {(c["dx"], c["dy"]) for c in norm_stack if c["role"] in WALL_ROLES}

    def nbr(dx, dy):
        return {"N": (dx, dy - 1) in floorset, "E": (dx + 1, dy) in floorset, "S": (dx, dy + 1) in floorset,
                "W": (dx - 1, dy) in floorset, "NE": (dx + 1, dy - 1) in floorset, "SE": (dx + 1, dy + 1) in floorset,
                "SW": (dx - 1, dy + 1) in floorset, "NW": (dx - 1, dy - 1) in floorset}
    import joel_block_adapter as JA
    gen_role, anchor = None, None
    for (dx, dy) in sorted(wallset, key=lambda c: (c[1], c[0])):
        r = JA.role_from_neighbors(nbr(dx, dy))
        if r:
            gen_role, anchor = r, {"x": dx, "y": dy}; break
    if gen_role is None and wallset:
        # pure wall mass (e.g. top cap with floor only well below): default by orientation
        ax = sorted(wallset, key=lambda c: (c[1], c[0]))[-1]
        gen_role = "wall_body" if orientation.startswith("north") else "lower_face_3_tile_stack"
        anchor = {"x": ax[0], "y": ax[1]}
    runid = f"jar_{entry['batch']}_{re.sub(r'[^a-z0-9]+', '_', entry['name'].lower())[:48]}"
    deco = len(masks["decorationMask"]) > 0 or len(masks["openingMask"]) > 0
    return {
        "runId": runid, "runName": entry["name"].replace(".tmx", ""),
        "sourcePatternFile": entry["path"], "sourceBatch": entry["batch"],
        "sourceReferenceMap": ("refrencemapmines1.tmx" if entry["batch"] == "batch_1" else "refrensmap2.tmx"),
        "sourceDimensions": [w, h], "runType": run_type, "structuralDesign": entry["name"].replace(".tmx", ""),
        "orientation": orientation, "width": x1 - x0 + 1, "height": y1 - y0 + 1,
        "anchor": anchor or {"x": 0, "y": 0}, "generatorRole": gen_role,
        "normalizedLayerStack": norm_stack,
        "originalLayerStack": original,
        "layerMismatches": mismatches,
        "tileIdsByStructuralRole": {k: sorted(v) for k, v in sorted(ids_by_role.items())},
        "tileIdsByLayer": {k: sorted(v) for k, v in sorted(ids_by_layer.items())},
        **masks,
        "requiredNeighborContext": ("floor on the " + orientation.split("/")[-1] + " side" if orientation != "unknown" else "floor-adjacent boundary"),
        "allowedPlacementContexts": [gen_role] if gen_role else [],
        "allowedRotations": ["none"], "allowTrimming": False, "allowRepeating": False,
        "compatibleTilesheets": ["mine"], "sourceConfidence": 80,
        "joelAuthored": True,
        "visualStatus": "joel_authored",
        "generatorStatus": "prototype_ready" if not deco else "review_needed",
        "locked": False,
        "decorationVariant": deco,
        "notes": (f"{len(mismatches)} layer cells normalized by tile-id role" if mismatches else "layers already canonical"),
    }


def main():
    for sub in ("raw", "normalized", "previews", "review"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    model = C.build_model()
    entries = discover()
    patterns = [e for e in entries if e["sourceType"] == "authored_pattern"]
    refs = [e for e in entries if e["sourceType"] == "authored_reference_map"]

    # Task 1 inventory
    inv = []
    for e in entries:
        d = parse_tmx(ROOT / e["path"])
        inv.append({**e, "dimensions": [d["w"], d["h"]], "layers": sorted(d["layers"]),
                    "tilesheets": d["tilesheets"], "tileCount": sum(len(g) for g in d["layers"].values()),
                    "parsed": True, "riskFlags": []})
    (OUT / "source_inventory.json").write_text(json.dumps({
        "generatedAt": TS, "patternFiles": len(patterns), "referenceMaps": len(refs),
        "batches": sorted({e["batch"] for e in entries}), "maps": inv}, indent=2), encoding="utf-8")

    # Task 2 tile-role map
    role_map, dir_hist = build_tile_role_map(model, patterns)
    (OUT / "normalized" / "tile_id_structural_role_map.json").write_text(json.dumps({
        "generatedAt": TS, "method": "tile-id structural role from geometry + sheet position + "
        "tilesheet Type property + corpus role model; NOT layer name.",
        "referenceMapsUsed": [r["name"] for r in refs], "tileCount": len(role_map),
        "roles": role_map}, indent=2), encoding="utf-8")

    # Task 3 + 4 normalization + runs
    runs = []
    for e in patterns:
        r = extract_run(e, role_map)
        if r:
            runs.append(r)
    normalized = [{"sourcePatternFile": r["sourcePatternFile"], "runName": r["runName"],
                   "layerMismatches": r["layerMismatches"],
                   "normalizedLayerStack": r["normalizedLayerStack"]} for r in runs]
    (OUT / "normalized" / "normalized_authored_patterns.json").write_text(json.dumps({
        "generatedAt": TS, "patternCount": len(normalized),
        "totalLayerMismatches": sum(len(r["layerMismatches"]) for r in runs),
        "patterns": normalized}, indent=2), encoding="utf-8")
    (OUT / "joel_authored_runs_v1.json").write_text(json.dumps({
        "generatedAt": TS, "scope": "joel_authored_mine_runs", "runCount": len(runs),
        "note": "One complete authored run per pattern. Whole structures only; never split into "
                "loose tiles. All prototype_ready/review_needed; none generator_ready/locked.",
        "runs": runs}, indent=2), encoding="utf-8")
    (OUT / "joel_authored_runs_v1_schema.json").write_text(json.dumps({
        "generatedAt": TS,
        "runTypes": ["top_wall_run", "top_wall_flowing_design", "top_wall_hard_corner_to_side",
                     "top_wall_soft_bend", "lower_face_run", "lower_face_soft_curve",
                     "lower_face_both_sides_curve", "left_wall_run", "right_wall_run", "wall_body_run",
                     "hard_corner", "soft_corner", "round_corner", "inner_corner", "outer_corner",
                     "angled_wall", "diagonal_transition", "ladder_entrance", "shaft_socket",
                     "entrance_socket", "shadow_strip", "wall_with_decoration_variant",
                     "support_beam_variant", "vine_variant", "torch_variant"],
        "requiredFields": ["runId", "runName", "sourcePatternFile", "sourceBatch", "runType",
                           "orientation", "width", "height", "anchor", "generatorRole",
                           "normalizedLayerStack", "originalLayerStack", "tileIdsByStructuralRole",
                           "wallMask", "floorMask", "visualStatus", "generatorStatus", "locked"],
        "masks": ["floorMask", "wallMask", "voidMask", "shadowMask", "openingMask",
                  "decorationMask", "collisionMask"]}, indent=2), encoding="utf-8")

    # reports
    REPORTS.mkdir(parents=True, exist_ok=True)
    by_type = collections.Counter(r["runType"] for r in runs)
    by_gen = collections.Counter(r["generatorRole"] for r in runs)
    rolecnt = collections.Counter(v["structuralRole"] for v in role_map.values())
    (REPORTS / "joel_authored_pattern_source_inventory.md").write_text(
        "# Joel Authored Pattern — Source Inventory\n\n"
        f"- Pattern files: **{len(patterns)}** | reference maps: **{len(refs)}** | batches: {sorted({e['batch'] for e in entries})}\n\n"
        "| file | batch | type | dims | layers |\n|---|---|---|---|---|\n"
        + "\n".join(f"| `{e['name']}` | {e['batch']} | {e['sourceType']} | {i['dimensions']} | {i['layers']} |"
                    for e, i in zip(entries, inv)) + "\n", encoding="utf-8")
    (REPORTS / "joel_authored_tile_id_role_map.md").write_text(
        "# Joel Authored — Tile-ID Structural Role Map\n\n"
        f"- Tiles classified: **{len(role_map)}** (by geometry + sheet position + Type property + corpus model)\n\n"
        "## Role counts\n\n| structuralRole | tiles |\n|---|--:|\n"
        + "\n".join(f"| {r} | {n} |" for r, n in rolecnt.most_common())
        + "\n\n## Top-wall cap tile IDs (sheet rows 0-2)\n\n"
        + ", ".join(str(v["localTileId"]) for v in role_map.values() if v["structuralRole"] == "top_wall_cap")
        + "\n", encoding="utf-8")
    (REPORTS / "joel_authored_pattern_normalization.md").write_text(
        "# Joel Authored — Pattern Normalization (content-based)\n\n"
        f"- Patterns normalized: **{len(runs)}**\n"
        f"- Total layer cells reassigned by tile-id role: **{sum(len(r['layerMismatches']) for r in runs)}**\n\n"
        "Wall tiles painted on `Back` (and other off-layer placements) are moved to their canonical "
        "layer by tile-id role, never by layer name. Originals are preserved.\n\n"
        "| pattern | mismatches | note |\n|---|--:|---|\n"
        + "\n".join(f"| `{r['runName']}` | {len(r['layerMismatches'])} | {r['notes']} |" for r in runs) + "\n",
        encoding="utf-8")
    (REPORTS / "joel_authored_runs_v1_summary.md").write_text(
        "# Joel Authored Runs v1 — Summary\n\n"
        f"- Runs created: **{len(runs)}** (one complete authored structure per pattern)\n"
        f"- Decoration-variant runs (review_needed): {sum(1 for r in runs if r['decorationVariant'])}\n\n"
        "## Run types\n\n| runType | count |\n|---|--:|\n"
        + "\n".join(f"| {t} | {n} |" for t, n in by_type.most_common())
        + "\n\n## Generator roles covered\n\n| generatorRole | runs |\n|---|--:|\n"
        + "\n".join(f"| {r} | {n} |" for r, n in by_gen.most_common()) + "\n", encoding="utf-8")

    print(json.dumps({"patterns": len(patterns), "refs": len(refs), "runs": len(runs),
                      "tileRoles": dict(rolecnt.most_common()),
                      "runTypes": dict(by_type.most_common()),
                      "generatorRoles": dict(by_gen.most_common()),
                      "layerMismatches": sum(len(r["layerMismatches"]) for r in runs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
