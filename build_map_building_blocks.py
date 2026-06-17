#!/usr/bin/env python3
"""
build_map_building_blocks.py  (READ-ONLY extraction)  --  MINES FIRST

Splits vanilla Mine maps into reusable, complete multi-layer building blocks (not
single-tile roles). Blocks are 3x3 (canonical wall/corner/floor unit) and 5x5 (room
fragment) windows anchored on every cell, each preserving the full Back/Buildings/Front
layer stack + masks. Blocks are clustered by EXACT multi-layer signature; only repeated
signatures (frequency >= MIN_FREQ across >= MIN_MAPS maps) become generator_ready.
Singletons go to quarantine/needs_review.

Scope: vanilla Mine corpus (mine tilesheet -> compatible with the generator's mine.png).
Moonvillage dungeon + outdoor/indoor are deferred to later passes.

No source modification, no production maps, no approved-DB writes.
"""
from __future__ import annotations
import json, sys, hashlib, collections
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINE_DIR = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
MBB = ROOT / "pattern_learning" / "map_building_blocks"
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402

VOID = {77, 135}
SIZES = [(3, 3), (5, 5)]
MIN_FREQ = 4          # a signature must repeat this many times to be reusable
MIN_MAPS = 3          # across at least this many distinct maps


def grids(path):
    mp = tbin_reader.parse(path.read_bytes())
    L = {l["id"]: l for l in mp["layers"]}
    if "Back" not in L:
        return None
    w, h = L["Back"]["layerSize"]
    def lid(n, x, y):
        ly = L.get(n)
        if not ly:
            return None
        v = ly["tiles"].get((x, y))
        return v[1] if v else None
    return w, h, lid


def cell_kind(lid, x, y):
    b = lid("Buildings", x, y)
    bk = lid("Back", x, y)
    wall = b is not None and b not in VOID
    if wall:
        return "wall"
    if bk is not None and bk not in VOID:   # Back tile 77/135 is deep void, not floor
        return "floor"
    return "void"


def classify_block(lid, cx, cy, wsz, hsz):
    """Classify a block by its center cell's boundary role + Front presence."""
    def kind(x, y):
        return cell_kind(lid, x, y)
    c = kind(cx, cy)
    if c == "floor":
        # all-floor 3x3 -> floor base/variation
        kinds = [kind(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        if all(k == "floor" for k in kinds):
            return "mine_floor_base"
        return "mine_floor_variation"
    if c == "void":
        return "mine_deep_void"
    # wall center: classify by floor neighbors
    N = kind(cx, cy - 1) == "floor"; S = kind(cx, cy + 1) == "floor"
    E = kind(cx + 1, cy) == "floor"; W = kind(cx - 1, cy) == "floor"
    card = {d for d, v in [("N", N), ("E", E), ("S", S), ("W", W)] if v}
    front = lid("Front", cx, cy)
    has_front = front is not None and front not in VOID
    if card == {"S"}:
        return "mine_wall_forward_lower_face"
    if card == {"N"}:
        return "mine_wall_back_top_edge"
    if card == {"E"}:
        return "mine_wall_left_edge"
    if card == {"W"}:
        return "mine_wall_right_edge"
    if card in ({"S", "E"}, {"S", "W"}, {"N", "E"}, {"N", "W"}):
        return "mine_inner_corner"
    if not card:
        diag = [(dx, dy) for dx, dy in [(1, 1), (-1, 1), (1, -1), (-1, -1)]
                if kind(cx + dx, cy + dy) == "floor"]
        if len(diag) == 1:
            return "mine_outer_corner"
        if len(diag) >= 2:
            return "mine_angled_wall"
        return "mine_wall_body"
    return "mine_blocked_boundary"


def extract_block(lid, cx, cy, wsz, hsz):
    """Capture a wsz x hsz window centred on (cx,cy) with full layer stacks + masks."""
    ax, ay = wsz // 2, hsz // 2
    cells = []
    floor_mask, wall_mask, void_mask, shadow_mask = [], [], [], []
    sig = []
    for dy in range(hsz):
        for dx in range(wsz):
            x, y = cx - ax + dx, cy - ay + dy
            stack = {}
            for layer in ("Back", "Buildings", "Front"):
                v = lid(layer, x, y)
                if v is not None:
                    stack[layer] = v
            k = cell_kind(lid, x, y)
            (floor_mask if k == "floor" else wall_mask if k == "wall" else void_mask).append([dx, dy])
            if "Front" in stack and stack["Front"] not in VOID:
                shadow_mask.append([dx, dy])
            if stack:
                cells.append({"dx": dx, "dy": dy, "stack": stack})
                sig.append((dx, dy, tuple(sorted((L, int(t)) for L, t in stack.items()))))
    signature = hashlib.md5(json.dumps(sorted(sig), default=str).encode()).hexdigest()[:16]
    return {
        "width": wsz, "height": hsz, "anchor": {"x": ax, "y": ay},
        "cells": cells, "floorMask": floor_mask, "wallMask": wall_mask,
        "voidMask": void_mask, "shadowMask": shadow_mask, "signature": signature,
    }


def main():
    for sub in ("raw_blocks", "by_size", "by_type", "clusters"):
        (MBB / sub).mkdir(parents=True, exist_ok=True)
    maps = sorted(MINE_DIR.glob("*.tbin"))
    clusters = {}   # signature -> aggregate
    type_counts = collections.Counter()
    size_counts = collections.Counter()
    total_blocks = 0
    for path in maps:
        g = grids(path)
        if not g:
            continue
        w, h, lid = g
        for (wsz, hsz) in SIZES:
            ax, ay = wsz // 2, hsz // 2
            for cy in range(ay, h - ay):
                for cx in range(ax, w - ax):
                    # only anchor on non-empty cells to avoid pure-void noise
                    if cell_kind(lid, cx, cy) == "void":
                        continue
                    blk = extract_block(lid, cx, cy, wsz, hsz)
                    if len(blk["cells"]) < 2:
                        continue
                    btype = classify_block(lid, cx, cy, wsz, hsz)
                    total_blocks += 1
                    key = (blk["signature"], wsz, hsz)
                    c = clusters.get(key)
                    if c is None:
                        c = clusters[key] = {
                            "signature": blk["signature"], "size": f"{wsz}x{hsz}",
                            "blockType": btype, "count": 0, "maps": set(),
                            "coords": [], "representative": blk,
                            "hasFront": len(blk["shadowMask"]) > 0,
                        }
                    c["count"] += 1
                    c["maps"].add(path.name)
                    if len(c["coords"]) < 6:
                        c["coords"].append({"map": path.name, "x": cx, "y": cy})

    # Build library from REPEATED clusters only.
    library = []
    cluster_out = []
    for (sig, wsz, hsz), c in sorted(clusters.items(), key=lambda kv: -kv[1]["count"]):
        repeated = c["count"] >= MIN_FREQ and len(c["maps"]) >= MIN_MAPS
        cluster_out.append({
            "clusterId": f"mbb_{c['blockType']}_{wsz}x{hsz}_{sig}",
            "blockType": c["blockType"], "size": c["size"], "count": c["count"],
            "maps": len(c["maps"]), "hasFront": c["hasFront"], "repeated": repeated,
        })
        type_counts[c["blockType"]] += 1
        size_counts[c["size"]] += 1
        if not repeated:
            continue
        rep = c["representative"]
        if not any(int(t) not in VOID for cell in rep["cells"] for t in cell["stack"].values()):
            continue   # void-only window: not reusable art, never promote
        library.append({
            "blockId": f"mbb_{c['blockType']}_{wsz}x{hsz}_{sig}",
            "blockType": c["blockType"], "profile": "mine",
            "sourceCategory": "vanilla_mine", "sourceTilesheet": "mine",
            "width": wsz, "height": hsz, "sizeClass": c["size"],
            "anchor": rep["anchor"], "cells": rep["cells"],
            "floorMask": rep["floorMask"], "wallMask": rep["wallMask"],
            "voidMask": rep["voidMask"], "shadowMask": rep["shadowMask"],
            "frequency": c["count"], "sourceMapCount": len(c["maps"]),
            "exampleSourceCoordinates": c["coords"],
            "hasFront": c["hasFront"],
            "confidence": min(99, 40 + c["count"]),
            "visualStatus": "proposed",
            "generatorStatus": "review_needed",   # promoted to generator_ready only after Joel review
            "locked": False,
            "recommendedUse": "review_needed",
        })

    ts = datetime.now(timezone.utc).isoformat()
    (MBB / "raw_blocks" / "all_raw_building_blocks.json").write_text(json.dumps({
        "generatedAt": ts, "scope": "vanilla_mine", "mapsScanned": len(maps),
        "totalBlockWindows": total_blocks, "uniqueSignatures": len(clusters),
        "note": "Per-signature representatives are in clusters/library; raw windows summarized by signature to stay bounded.",
        "sampleClusters": cluster_out[:500],
    }, indent=2), encoding="utf-8")
    (MBB / "clusters" / "building_block_clusters.json").write_text(json.dumps({
        "generatedAt": ts, "clusterCount": len(clusters),
        "repeatedClusters": sum(1 for c in cluster_out if c["repeated"]),
        "clusters": cluster_out,
    }, indent=2), encoding="utf-8")
    by_type = collections.defaultdict(list)
    for b in library:
        by_type[b["blockType"]].append(b["blockId"])
    (MBB / "by_type" / "building_blocks_by_type.json").write_text(json.dumps({
        "generatedAt": ts, "byType": {k: {"count": len(v), "blockIds": v[:50]} for k, v in sorted(by_type.items())},
    }, indent=2), encoding="utf-8")
    by_size = collections.defaultdict(list)
    for b in library:
        by_size[b["sizeClass"]].append(b["blockId"])
    (MBB / "by_size" / "building_blocks_by_size.json").write_text(json.dumps({
        "generatedAt": ts, "bySize": {k: {"count": len(v)} for k, v in sorted(by_size.items())},
    }, indent=2), encoding="utf-8")
    (MBB / "building_block_library.json").write_text(json.dumps({
        "generatedAt": ts, "scope": "vanilla_mine", "blockCount": len(library),
        "note": "Repeated multi-layer mine blocks. All review_needed until Joel approves; none auto-promoted to generator_ready.",
        "blocks": library,
    }, indent=2), encoding="utf-8")

    # Reports
    lib_by_type = collections.Counter(b["blockType"] for b in library)
    lines = ["# Map Building Blocks — Type Summary (mines)", "",
             f"- Scope: vanilla Mine ({len(maps)} maps)",
             f"- Block windows scanned: {total_blocks:,} | unique signatures: {len(clusters):,}",
             f"- Repeated reusable blocks (freq>={MIN_FREQ}, maps>={MIN_MAPS}): **{len(library)}**", "",
             "## Reusable blocks by type", "", "| blockType | reusable blocks |", "|---|---:|"]
    for t, n in lib_by_type.most_common():
        lines.append(f"| {t} | {n} |")
    (REPORTS / "map_building_blocks_type_summary.md").write_text("\n".join(lines), encoding="utf-8")
    (REPORTS / "map_building_blocks_size_summary.md").write_text(
        "# Map Building Blocks — Size Summary (mines)\n\n"
        + "\n".join(f"- {k}: {len(v)} reusable blocks" for k, v in sorted(by_size.items())) + "\n",
        encoding="utf-8")

    print(json.dumps({
        "mapsScanned": len(maps), "totalBlockWindows": total_blocks,
        "uniqueSignatures": len(clusters), "reusableBlocks": len(library),
        "reusableByType": dict(lib_by_type.most_common()),
        "reusableBySize": {k: len(v) for k, v in sorted(by_size.items())},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
