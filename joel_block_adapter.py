#!/usr/bin/env python3
"""
joel_block_adapter.py  (READ-ONLY)

Adapts Joel-approved LOCKED building blocks into the Smart Edge-Wrapper v2 template
schema. Roles are derived from each block's *center floor-neighbour geometry* (not the
block-type label), using the same classification the generator uses to classify boundary
cells -- so a converted block's internal wall/floor layout matches the boundary cell it is
placed on.

Only blocks with visualStatus=Joel_approved, generatorStatus=generator_ready, locked=true
are converted. Decoration variants (prototype_ready), review-needed openings, and anything
unapproved (floors, quarantine) are excluded and counted.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import mbb_common as C  # noqa: E402

LOCKED = ROOT / "pattern_learning" / "map_building_blocks" / "cleaned_blocks" / "joel_approved_building_blocks_v1.locked.json"


def role_from_neighbors(n: dict) -> str | None:
    """Mirror of build_smart_edge_wrapper_v2.classify(): floor-neighbour pattern -> role."""
    card = {d for d in ("N", "E", "S", "W") if n[d]}
    diag = {d for d in ("NE", "SE", "SW", "NW") if n[d]}
    if card == {"E"}:
        return "left_wall_edge"
    if card == {"W"}:
        return "right_wall_edge"
    if card == {"S", "E"}:
        return "lower_left_inner_corner"
    if card == {"S", "W"}:
        return "lower_right_inner_corner"
    if card == {"N", "E"}:
        return "upper_left_inner_corner"
    if card == {"N", "W"}:
        return "upper_right_inner_corner"
    if not card and len(diag) == 1:
        return {"SE": "upper_left_outer_corner", "SW": "upper_right_outer_corner",
                "NE": "lower_left_outer_corner", "NW": "lower_right_outer_corner"}[next(iter(diag))]
    if card == {"N"}:
        return "wall_body"               # generator's exposed-north-top role
    if card == {"S"}:
        return "lower_face_3_tile_stack"
    return None                          # interior wall / ambiguous -> not a boundary role


def derive_role(block, model):
    grid = {(c["dx"], c["dy"]): c["stack"] for c in block["cells"]}
    ax, ay = block["anchor"]["x"], block["anchor"]["y"]

    def floor_at(dx, dy):
        st = grid.get((ax + dx, ay + dy))
        return st is not None and C.cell_role(model, st) == "floor"

    n = {"N": floor_at(0, -1), "E": floor_at(1, 0), "S": floor_at(0, 1), "W": floor_at(-1, 0),
         "NE": floor_at(1, -1), "SE": floor_at(1, 1), "SW": floor_at(-1, 1), "NW": floor_at(-1, -1)}
    return role_from_neighbors(n)


def convert_block(block, model):
    role = derive_role(block, model)
    if role is None:
        return None
    ax, ay = block["anchor"]["x"], block["anchor"]["y"]
    layer_stack, ids = [], {"Back": set(), "Buildings": set(), "Front": set()}
    for c in block["cells"]:
        st = {}
        for layer in ("Back", "Buildings", "Front"):
            if layer in c["stack"]:
                tid = int(c["stack"][layer])
                st[layer] = {"localTileId": tid}
                ids[layer].add(tid)
        layer_stack.append({"dx": c["dx"] - ax, "dy": c["dy"] - ay, "stack": st})
    src = (block.get("exampleSource") or [{}])[0]
    return {
        "templateId": block.get("cleanedBlockId") or block["blockId"],
        "role": role, "tileIdFamilyId": "joel_approved_v1",
        "size": block["sizeClass"], "confidence": 100,
        "productionStatus": "generator_ready", "structuralDesign": block["blockType"],
        "sourceClusterId": block["blockId"], "anchor": {"x": ax, "y": ay},
        "layerStack": layer_stack,
        "tileIdsByLayer": {k: sorted(v) for k, v in ids.items()},
        "blockType": block["blockType"],
        "originalBlockId": block["blockId"],
        "sourceMap": src.get("map"),
        "sourceCoordinate": {"x": src.get("x"), "y": src.get("y")},
        "areaCells": block["width"] * block["height"],
        "joelVisualStatus": block.get("visualStatus"),
        "locked": block.get("locked", True),
    }


def load_joel_templates(path=LOCKED):
    """Returns (templates_by_role, stats)."""
    model = C.build_model()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    blocks = data["blocks"]
    by_role: dict[str, list] = {}
    stats = {
        "libraryPath": str(Path(path)), "totalBlocksInLockedLibrary": len(blocks),
        "coreEligible": 0, "decorationVariantsSkipped": 0, "reviewNeededOpeningsSkipped": 0,
        "otherSkipped": 0, "convertedToBoundaryRole": 0, "interiorOrAmbiguousSkipped": 0,
        "roleCounts": {}, "blockTypeConverted": {}, "interiorWallBodyBlocks": 0,
    }
    for b in blocks:
        eligible = (b.get("visualStatus") == "Joel_approved"
                    and b.get("generatorStatus") == "generator_ready"
                    and b.get("locked") is True)
        if not eligible:
            gs = b.get("generatorStatus")
            if gs == "prototype_ready":
                stats["decorationVariantsSkipped"] += 1
            elif gs == "review_needed":
                stats["reviewNeededOpeningsSkipped"] += 1
            else:
                stats["otherSkipped"] += 1
            continue
        stats["coreEligible"] += 1
        conv = convert_block(b, model)
        if conv is None:
            stats["interiorOrAmbiguousSkipped"] += 1
            if b["blockType"] == "mine_wall_body":
                stats["interiorWallBodyBlocks"] += 1
            continue
        by_role.setdefault(conv["role"], []).append(conv)
        stats["convertedToBoundaryRole"] += 1
        stats["blockTypeConverted"][b["blockType"]] = stats["blockTypeConverted"].get(b["blockType"], 0) + 1
    # smallest-block-first within each role (less placement overlap), stable by id
    for role in by_role:
        by_role[role].sort(key=lambda t: (t["areaCells"], t["templateId"]))
    stats["roleCounts"] = {r: len(v) for r, v in sorted(by_role.items())}
    return by_role, stats


if __name__ == "__main__":
    by_role, stats = load_joel_templates()
    print(json.dumps(stats, indent=2))
