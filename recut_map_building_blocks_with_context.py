#!/usr/bin/env python3
"""
recut_map_building_blocks_with_context.py  (READ-ONLY w.r.t. sources)

For blocks flagged `cropped_structure` / `too_small_for_structure` /
`needs_larger_context` (and whose type is recut-eligible), re-read the ORIGINAL source
.tbin at the block's recorded anchor and capture a LARGER window (5x5, then 7x7) centred
on the same cell, so a structure the 3x3 cut in half is shown whole. Each re-cut is
re-scored; the smallest window that resolves the structure (cropQuality >= target and the
type's structural score clears its bar) is kept. Source maps are never modified.

Output: cleaned_blocks/recut_blocks.json
"""
from __future__ import annotations
import json, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINE_DIR = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
SCORED = CLEANED / "scored_building_blocks.json"
RULES = CLEANED / "block_cleaning_rules.json"
OUT = CLEANED / "recut_blocks.json"
sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402
import mbb_common as C  # noqa: E402
import score_map_building_blocks as S  # noqa: E402

RECUT_SIZES = [5, 7]
TARGET_CROP = 0.6
_grids_cache = {}


def grids(mapname):
    if mapname in _grids_cache:
        return _grids_cache[mapname]
    path = MINE_DIR / mapname
    if not path.exists():
        _grids_cache[mapname] = None
        return None
    mp = tbin_reader.parse(path.read_bytes())
    L = {l["id"]: l for l in mp["layers"]}
    if "Back" not in L:
        _grids_cache[mapname] = None
        return None
    w, h = L["Back"]["layerSize"]

    def lid(n, x, y):
        ly = L.get(n)
        if not ly:
            return None
        v = ly["tiles"].get((x, y))
        return v[1] if v else None

    _grids_cache[mapname] = (w, h, lid)
    return _grids_cache[mapname]


def cut_window(lid, cx, cy, size, model):
    """Build a block dict (cells + masks) for a size x size window centred on (cx,cy)."""
    a = size // 2
    cells, floor_mask, wall_mask, void_mask, shadow_mask, sig = [], [], [], [], [], []
    for dy in range(size):
        for dx in range(size):
            x, y = cx - a + dx, cy - a + dy
            stack = {}
            for layer in ("Back", "Buildings", "Front"):
                v = lid(layer, x, y)
                if v is not None:
                    stack[layer] = v
            role = C.cell_role(model, stack)
            if role == "floor":
                floor_mask.append([dx, dy])
            elif role in ("wall", "object", "opening"):
                wall_mask.append([dx, dy])
            else:
                void_mask.append([dx, dy])
            if C.front_kind(model, stack) != "none":
                shadow_mask.append([dx, dy])
            if stack:
                cells.append({"dx": dx, "dy": dy, "stack": stack})
                sig.append((dx, dy, tuple(sorted((L, int(t)) for L, t in stack.items()))))
    signature = hashlib.md5(json.dumps(sorted(sig), default=str).encode()).hexdigest()[:16]
    return {
        "width": size, "height": size, "anchor": {"x": a, "y": a}, "cells": cells,
        "floorMask": floor_mask, "wallMask": wall_mask, "voidMask": void_mask,
        "shadowMask": shadow_mask, "signature": signature,
    }


def main():
    model = C.build_model()
    scored = json.loads(SCORED.read_text(encoding="utf-8"))["scored"]
    rules = json.loads(RULES.read_text(encoding="utf-8"))["types"]
    by_id = {s["blockId"]: s for s in scored}

    recut_flags = {"cropped_structure", "too_small_for_structure", "needs_larger_context"}
    candidates = [s for s in scored
                  if (recut_flags & set(s["riskFlags"]))
                  and rules.get(s["blockType"], {}).get("recutEligible")]

    out = []
    resolved = unresolved = no_source = 0
    for s in candidates:
        bt = s["blockType"]
        src = (s.get("exampleSource") or [{}])[0]
        mapname, cx, cy = src.get("map"), src.get("x"), src.get("y")
        if not mapname or cx is None:
            no_source += 1
            continue
        g = grids(mapname)
        if not g:
            no_source += 1
            continue
        w, h, lid = g
        orig_size = max(s["width"], s["height"])
        best = None
        for size in RECUT_SIZES:
            if size <= orig_size:
                continue
            blk = cut_window(lid, cx, cy, size, model)
            blk["blockType"] = bt
            blk["sizeClass"] = f"{size}x{size}"
            sc, flags, counts = S.score_block(model, blk)
            crop = sc["cropQualityScore"]
            # structural-resolution test depends on type family
            if bt in S.CORNER_TYPES:
                struct_ok = sc["cornerCompletenessScore"] >= rules[bt].get("minCornerCompleteness", 0.4)
            elif bt in S.EDGE_TYPES:
                struct_ok = sc["edgeCompletenessScore"] >= rules[bt].get("minEdgeCompleteness", 0.6)
            elif bt == "mine_wall_body":
                struct_ok = (sc["wallPurityScore"] >= rules[bt].get("minWallPurity", 0.45)
                             and counts["floor"] + counts["void"] > 0)
            else:
                struct_ok = sc["classificationConfidence"] >= 0.5
            ok = crop >= TARGET_CROP and struct_ok and "cropped_structure" not in flags
            rec = {"size": size, "scores": sc, "flags": flags, "roleCounts": counts,
                   "structureResolved": ok, "block": blk}
            if best is None or (ok and not best["structureResolved"]) or \
               (ok == best["structureResolved"] and sc["reusableGeneratorScore"] > best["scores"]["reusableGeneratorScore"]):
                best = rec
            if ok:
                break
        if best is None:
            no_source += 1
            continue
        cleaned_id = f"{s['blockId']}__rc{best['size']}x{best['size']}_{best['block']['signature']}"
        out.append({
            "originalBlockId": s["blockId"], "cleanedBlockId": cleaned_id,
            "blockType": bt, "sourceMap": mapname, "sourceAnchor": {"x": cx, "y": cy},
            "originalSize": s["sizeClass"], "recutSize": best["block"]["sizeClass"],
            "structureResolved": best["structureResolved"],
            "originalReusable": s["scores"]["reusableGeneratorScore"],
            "recutReusable": best["scores"]["reusableGeneratorScore"],
            "originalCropQuality": s["scores"]["cropQualityScore"],
            "recutCropQuality": best["scores"]["cropQualityScore"],
            "recutScores": best["scores"], "recutFlags": best["flags"],
            "recutRoleCounts": best["roleCounts"],
            "width": best["block"]["width"], "height": best["block"]["height"],
            "anchor": best["block"]["anchor"], "cells": best["block"]["cells"],
            "floorMask": best["block"]["floorMask"], "wallMask": best["block"]["wallMask"],
            "voidMask": best["block"]["voidMask"], "shadowMask": best["block"]["shadowMask"],
            "signature": best["block"]["signature"],
        })
        if best["structureResolved"]:
            resolved += 1
        else:
            unresolved += 1

    CLEANED.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "candidatesConsidered": len(candidates),
        "recut": len(out), "structureResolved": resolved,
        "structureUnresolved": unresolved, "noSourceOrEdge": no_source,
        "recutSizesTried": RECUT_SIZES, "targetCropQuality": TARGET_CROP,
        "blocks": out,
    }, indent=2), encoding="utf-8")
    print(json.dumps({
        "candidates": len(candidates), "recut": len(out),
        "resolved": resolved, "unresolved": unresolved, "noSourceOrEdge": no_source,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
