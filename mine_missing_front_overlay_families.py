#!/usr/bin/env python3
"""
mine_missing_front_overlay_families.py  (READ-ONLY mining)

Mines paired Front-overlay families for mine/dungeon boundary roles from the vanilla
Mine maps (mine tilesheet, the sheet the generator renders) and reports Moonvillage
Dungeon evidence separately (different tilesheets -> not generator-ready for mine.png).

A family is the empirical answer to: "for boundary role R, at which offset does vanilla
place a Front overlay tile, which Front id, and over which paired Buildings/Back context?"
Only families with repeated evidence AND a clear paired context are marked generator_ready.

Probe finding that motivates this: Front is sparse AT the wall cell, but wall_top casts a
Front shadow on the floor to its north (offset (0,-1)) in ~61% of cases; edges carry
moderate overlays; lower_face/outer_corner have ~no Front family in vanilla.

Outputs (extend the fresh relearn DB; nothing rebuilt):
  raw_windows/missing_front_overlay_windows.json
  clusters/missing_front_overlay_clusters.json
  clusters/missing_front_overlay_tile_id_families.json
  templates/missing_front_overlay_template_pack.json
Read-only on all map sources. No production maps, no mission_assets edits.
"""
from __future__ import annotations
import json, sys, glob, re, collections, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEARN = ROOT / "pattern_learning" / "mine_dungeon_fresh_relearn"
MINE_DIR = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
DUNGEON_DIR = ROOT / "mission_assets" / "moonvillage" / "maps" / "MainMoonvillage-git" / "[CP] Moonvillage" / "assets" / "Maps" / "Dungeon"
sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402

VOID = {77, 135}
# Boundary role -> the Front-overlay offset(s) to learn (where vanilla casts the overlay).
ROLE_OFFSETS = {
    "wall_top": [(0, -1), (0, 0)],          # cast shadow on floor to the north + on-cell
    "left_edge": [(0, 0), (0, 1), (0, -1)],
    "right_edge": [(0, 0), (0, 1), (0, -1)],
    "lower_face": [(0, 0), (0, 1)],
    "outer_corner": [(0, 0)],
    "ladder_opening": [(0, 0), (0, -1)],
}
GENERATOR_READY_MIN_COVERAGE = 0.15   # >=15% of role cells carry the overlay
GENERATOR_READY_MIN_COUNT = 20        # and at least 20 occurrences


def grids_from_tbin(path):
    mp = tbin_reader.parse(path.read_bytes())
    L = {l["id"]: l for l in mp["layers"]}
    if "Back" not in L:
        return None
    w, h = L["Back"]["layerSize"]
    sheet = next((ts.get("imageSource", "") for ts in mp.get("tilesheets", [])), "")
    def lid(n, x, y):
        ly = L.get(n)
        if not ly:
            return None
        v = ly["tiles"].get((x, y))
        return v[1] if v else None
    return w, h, lid, sheet


def grids_from_tmx(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    mm = re.search(r'<map\b[^>]*?\bwidth="(\d+)"\s+height="(\d+)"', txt)
    if not mm:
        return None
    w, hh = int(mm.group(1)), int(mm.group(2))
    fg = sorted(int(g) for g in re.findall(r'<tileset firstgid="(\d+)"', txt))
    sheet = (re.search(r'<image source="([^"]+)"', txt) or [None, ""])[1]
    layers = {}
    for lm in re.finditer(r'<layer[^>]*name="([^"]+)"[^>]*>\s*<data encoding="csv">\s*(.*?)\s*</data>', txt, re.S):
        nums = [int(v) for v in lm.group(2).replace("\n", "").split(",") if v.strip() != ""]
        layers[lm.group(1)] = nums
    base = fg[0] if fg else 1
    def lid(n, x, y):
        g = layers.get(n)
        if not g or not (0 <= x < w and 0 <= y < hh):
            return None
        gid = g[y * w + x]
        return (gid - base) if gid else None
    return w, hh, lid, sheet


def classify_role(lid, x, y):
    def wall(xx, yy):
        b = lid("Buildings", xx, yy)
        return b is not None and b not in VOID
    def floor(xx, yy):
        bk = lid("Back", xx, yy)
        return bk is not None and not wall(xx, yy)
    if not wall(x, y):
        return None
    card = {d for d, v in [("N", floor(x, y - 1)), ("E", floor(x + 1, y)),
                           ("S", floor(x, y + 1)), ("W", floor(x - 1, y))] if v}
    if card == {"N"}:
        return "wall_top"
    if card == {"E"}:
        return "left_edge"
    if card == {"W"}:
        return "right_edge"
    if card == {"S"}:
        return "lower_face"
    if not card:
        diag = [(dx, dy) for dx, dy in [(1, 1), (-1, 1), (1, -1), (-1, -1)] if floor(x + dx, y + dy)]
        if len(diag) == 1:
            return "outer_corner"
    return None


def mine_source(path, reader, want_sheet_match):
    res = reader(path)
    if not res:
        return [], collections.Counter()
    w, h, lid, sheet = res
    windows = []
    role_total = collections.Counter()
    for y in range(h):
        for x in range(w):
            role = classify_role(lid, x, y)
            if role is None:
                continue
            role_total[role] += 1
            bld = lid("Buildings", x, y)
            for dx, dy in ROLE_OFFSETS.get(role, []):
                f = lid("Front", x + dx, y + dy)
                if f is not None and f not in VOID:
                    back = lid("Back", x + dx, y + dy)
                    windows.append({
                        "sourceMap": path.name, "sourceTilesheet": sheet,
                        "x": x, "y": y, "role": role, "offset": [dx, dy],
                        "frontId": f, "pairedBuildingsId": bld,
                        "pairedBackId": back,
                    })
    return windows, role_total


def main():
    (RELEARN / "raw_windows").mkdir(parents=True, exist_ok=True)
    (RELEARN / "clusters").mkdir(parents=True, exist_ok=True)
    (RELEARN / "templates").mkdir(parents=True, exist_ok=True)

    vanilla = sorted(p for p in MINE_DIR.glob("*.tbin"))
    dungeon = sorted(DUNGEON_DIR.glob("*.tmx")) if DUNGEON_DIR.exists() else []

    windows = []
    role_total = collections.Counter()
    for p in vanilla:
        win, rt = mine_source(p, grids_from_tbin, True)
        windows += win
        role_total += rt
    dungeon_windows = []
    for p in dungeon:
        win, _ = mine_source(p, grids_from_tmx, False)
        dungeon_windows += win

    # Cluster vanilla windows -> families keyed by (role, offset). Each family is a WEIGHTED
    # front-id picker (vanilla uses many shadow-tile variants per boundary), with paired context.
    clusters = collections.defaultdict(lambda: {"frontIds": collections.Counter(), "pairedBuildings": collections.Counter(),
                                                "pairedBack": collections.Counter(), "maps": set(), "coords": [], "cellsWith": set()})
    for win in windows:
        key = (win["role"], tuple(win["offset"]))
        c = clusters[key]
        c["frontIds"][win["frontId"]] += 1
        c["pairedBuildings"][win["pairedBuildingsId"]] += 1
        c["pairedBack"][win["pairedBackId"]] += 1
        c["maps"].add(win["sourceMap"])
        c["cellsWith"].add((win["sourceMap"], win["x"], win["y"]))
        if len(c["coords"]) < 6:
            c["coords"].append([win["x"], win["y"]])

    # Keep, per role, only the single best offset (highest coverage) as the family.
    best_by_role = {}
    for (role, offset), c in clusters.items():
        cov = len(c["cellsWith"]) / (role_total[role] or 1)
        if role not in best_by_role or cov > best_by_role[role][1]:
            best_by_role[role] = ((role, offset), cov, c)

    families = []
    for role, ((_, offset), coverage, c) in best_by_role.items():
        n_maps = len(c["maps"])
        count = len(c["cellsWith"])
        if coverage >= 0.30 and count >= GENERATOR_READY_MIN_COUNT and n_maps >= 5:
            use = "generator_ready"
        elif coverage >= 0.12 and count >= 10:
            use = "manual_review"
        else:
            use = "reject"
        top_fronts = c["frontIds"].most_common(8)
        families.append({
            "familyId": f"front_overlay_{role}_off{offset[0]}_{offset[1]}",
            "familyName": f"{role} front overlay @ offset {offset}",
            "structuralDesign": {
                "wall_top": "wall_top_cast_shadow", "left_edge": "left_edge_overlay",
                "right_edge": "right_edge_overlay", "lower_face": "lower_face_shadow",
                "outer_corner": "outer_corner_overlay", "ladder_opening": "ladder_opening_overlay",
            }.get(role, role),
            "role": role,
            "offset": list(offset),
            "frontTileIdsWeighted": top_fronts,        # [(id, count), ...] -> weighted picker
            "primaryFrontTileId": top_fronts[0][0] if top_fronts else None,
            "pairedBuildingsTileIds": [k for k, _ in c["pairedBuildings"].most_common(4) if k is not None],
            "pairedBackTileIds": [k for k, _ in c["pairedBack"].most_common(4) if k is not None],
            "frequency": count,
            "coverageOfRole": round(coverage, 3),
            "sourceMapCount": n_maps,
            "exampleSourceCoordinates": c["coords"],
            "sourceTilesheet": "mine",
            "confidence": min(99, int(40 + coverage * 90)),
            "recommendedUse": use,
        })
    families.sort(key=lambda f: -f["coverageOfRole"])

    generator_ready = [f for f in families if f["recommendedUse"] == "generator_ready"]

    (RELEARN / "raw_windows" / "missing_front_overlay_windows.json").write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "vanillaMapsScanned": len(vanilla), "dungeonMapsScanned": len(dungeon),
        "roleTotals": dict(role_total),
        "windowCountVanilla": len(windows), "windowCountDungeon": len(dungeon_windows),
        "windows": windows[:4000],
        "dungeonWindowsSample": dungeon_windows[:1000],
    }, indent=2), encoding="utf-8")
    (RELEARN / "clusters" / "missing_front_overlay_clusters.json").write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "clusterCount": len(clusters),
        "clusters": [{"role": k[0], "offset": list(k[1]), "cells": len(v["cellsWith"]),
                      "topFrontIds": v["frontIds"].most_common(6), "maps": len(v["maps"])}
                     for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1]["cellsWith"]))][:300],
    }, indent=2), encoding="utf-8")
    (RELEARN / "clusters" / "missing_front_overlay_tile_id_families.json").write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "roleTotals": dict(role_total),
        "familyCount": len(families), "generatorReadyCount": len(generator_ready),
        "families": families,
    }, indent=2), encoding="utf-8")

    # Promote generator-ready families into a paired overlay template pack.
    pack = []
    for f in generator_ready:
        pack.append({
            "templateId": f"overlay_{f['familyId']}",
            "sourceFamilyId": f["familyId"],
            "structuralDesign": f["structuralDesign"],
            "role": f["role"],
            "size": "1x1",
            "overlayOffset": f["offset"],
            "primaryFrontTileId": f["primaryFrontTileId"],
            "frontTileIdsWeighted": f["frontTileIdsWeighted"],
            "pairedBuildingsContext": f["pairedBuildingsTileIds"],
            "pairedBackContext": f["pairedBackTileIds"],
            "placementRules": "stamp Front overlay at offset relative to the base boundary cell only if "
                              "the target cell is floor and the base wall cell carries a paired Buildings id",
            "neighborRules": f"requires {f['role']} boundary geometry",
            "allowedRotations": ["none"],
            "tilesheetCompatibility": "mine",
            "confidence": f["confidence"],
            "sourceEvidence": {"frequency": f["frequency"], "coverage": f["coverageOfRole"], "maps": f["sourceMapCount"]},
            "productionStatus": "generator_ready",
        })
    (RELEARN / "templates" / "missing_front_overlay_template_pack.json").write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "note": "Paired Front-overlay templates. Each stamps ONE Front tile at an offset relative to a "
                "placed base boundary template, only with matching paired context. Not loose: the overlay "
                "requires its base wall template + the documented floor/Buildings context.",
        "templates": pack,
    }, indent=2), encoding="utf-8")

    print(json.dumps({
        "vanillaMaps": len(vanilla), "dungeonMaps": len(dungeon),
        "windows": len(windows), "families": len(families),
        "generatorReady": len(generator_ready),
        "generatorReadyFamilies": [(f["role"], f["offset"], f["primaryFrontTileId"], f["frequency"], f["coverageOfRole"]) for f in generator_ready],
        "manualReviewFamilies": [(f["role"], f["offset"], f["coverageOfRole"]) for f in families if f["recommendedUse"] == "manual_review"],
        "rejectedRoles": [f["role"] for f in families if f["recommendedUse"] == "reject"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
