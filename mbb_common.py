#!/usr/bin/env python3
"""
mbb_common.py  (READ-ONLY helpers, shared)

Shared foundations for the building-block cleaning pass:
  - the data-driven tile-role model (which Buildings ids are walls vs objects/
    ladders, which Back ids are floor vs void, which Front ids are shadow vs decor),
    derived from the vanilla Mine corpus by connected-component analysis;
  - per-cell role helpers used by the scorer, re-cutter, and validator.

No source maps, mission_assets, unpacked basegame, or approved DB are modified.
The model is computed once and cached to cleaned_blocks/tile_role_model.json.
"""
from __future__ import annotations
import json, sys, collections, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINE_DIR = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
MODEL_PATH = CLEANED / "tile_role_model.json"
sys.path.insert(0, str(ROOT))
import tbin_reader  # noqa: E402

VOID = {77, 135}              # deep void / "no tile" on Back and Buildings
SHADOW_FRONT = {214, 215}     # canonical wall cast-shadow pair (verified custom_10)
OBJECT_COMP_MAX = 8           # Buildings ids whose median component <= this are props/objects
LADDER_IDS = {221}            # down-shaft / ladder sprite (an opening, not a wall)


def _scan_corpus():
    maps = sorted(MINE_DIR.glob("*.tbin"))
    comp_sizes = collections.defaultdict(list)
    back_ids = collections.Counter()
    bld_ids = collections.Counter()
    front_ids = collections.Counter()
    for p in maps:
        mp = tbin_reader.parse(p.read_bytes())
        L = {l["id"]: l for l in mp["layers"]}
        if "Buildings" not in L:
            continue
        bld = {xy: v[1] for xy, v in L["Buildings"]["tiles"].items()}
        for xy, v in L.get("Back", {"tiles": {}})["tiles"].items():
            back_ids[v[1]] += 1
        for xy, v in L["Buildings"]["tiles"].items():
            bld_ids[v[1]] += 1
        for xy, v in L.get("Front", {"tiles": {}})["tiles"].items():
            front_ids[v[1]] += 1
        seen = set()
        for xy, idx in bld.items():
            if idx in VOID or xy in seen:
                continue
            stack = [xy]; comp = []; seen.add(xy)
            while stack:
                cx, cy = stack.pop(); comp.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if (nx, ny) in bld and (nx, ny) not in seen and bld[(nx, ny)] not in VOID:
                        seen.add((nx, ny)); stack.append((nx, ny))
            for (cx, cy) in comp:
                comp_sizes[bld[(cx, cy)]].append(len(comp))
    return maps, comp_sizes, back_ids, bld_ids, front_ids


def build_model(force: bool = False) -> dict:
    if MODEL_PATH.exists() and not force:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    maps, comp_sizes, back_ids, bld_ids, front_ids = _scan_corpus()
    object_ids, wall_ids = set(), set()
    for idx, sizes in comp_sizes.items():
        med = statistics.median(sizes)
        if idx in LADDER_IDS:
            continue
        if med <= OBJECT_COMP_MAX:
            object_ids.add(idx)
        else:
            wall_ids.add(idx)
    back_floor_ids = {i for i in back_ids if i not in VOID}
    front_overlay_other = {i for i in front_ids if i not in VOID and i not in SHADOW_FRONT}
    model = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scope": "vanilla_mine",
        "mapsScanned": len(maps),
        "method": "connected-component analysis of the Buildings layer; "
                  "small-median-component ids are props/objects, large are wall structure.",
        "voidIds": sorted(VOID),
        "ladderIds": sorted(LADDER_IDS),
        "buildingsObjectIds": sorted(object_ids),
        "buildingsWallIds": sorted(wall_ids),
        "backVoidIds": sorted(VOID & set(back_ids)),
        "backFloorIds": sorted(back_floor_ids),
        "frontShadowIds": sorted(SHADOW_FRONT),
        "frontOverlayOtherIds": sorted(front_overlay_other),
        "objectCompMax": OBJECT_COMP_MAX,
    }
    CLEANED.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model


# ---- per-cell role helpers (operate on a model dict + a cell stack) ----

def _as_set(model, key):
    return set(model[key])


def cell_role(model, stack: dict) -> str:
    """Classify one cell's stack into: void | floor | wall | object | opening."""
    void = _as_set(model, "voidIds")
    objs = _as_set(model, "buildingsObjectIds")
    walls = _as_set(model, "buildingsWallIds")
    ladders = _as_set(model, "ladderIds")
    back = stack.get("Back")
    bld = stack.get("Buildings")
    bld_real = bld is not None and bld not in void
    if bld_real and bld in ladders:
        return "opening"
    if bld_real and bld in objs:
        return "object"
    if bld_real and (bld in walls or bld not in objs):
        # any non-void, non-object Buildings tile is structural wall
        return "wall"
    # no real Buildings tile -> floor if Back is real, else void
    if back is not None and back not in void:
        return "floor"
    return "void"


def front_kind(model, stack: dict) -> str:
    """none | shadow | decor for the Front layer of one cell."""
    void = _as_set(model, "voidIds")
    shadow = _as_set(model, "frontShadowIds")
    f = stack.get("Front")
    if f is None or f in void:
        return "none"
    return "shadow" if f in shadow else "decor"


def cells_to_grid(block) -> dict:
    """Map (dx,dy) -> stack for quick lookup."""
    return {(c["dx"], c["dy"]): c["stack"] for c in block["cells"]}


if __name__ == "__main__":
    m = build_model(force="--force" in sys.argv)
    print(json.dumps({
        "mapsScanned": m["mapsScanned"],
        "buildingsObjectIds": m["buildingsObjectIds"],
        "buildingsWallIds_count": len(m["buildingsWallIds"]),
        "backFloorIds_count": len(m["backFloorIds"]),
        "frontShadowIds": m["frontShadowIds"],
        "frontOverlayOtherIds_count": len(m["frontOverlayOtherIds"]),
    }, indent=2))
