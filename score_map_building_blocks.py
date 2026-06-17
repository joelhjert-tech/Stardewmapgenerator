#!/usr/bin/env python3
"""
score_map_building_blocks.py  (READ-ONLY)

Scores every extracted mine building block for structural completeness and
contamination, using the data-driven tile-role model (mbb_common). Each block gets
12 quality scores in [0,1] (higher = cleaner / more generator-worthy) and a set of
risk flags. Output feeds the cleaning/quarantine step and the contact sheets.

Scores are geometric + role-based (no opinions): they are computed from the block's
own layer stacks and the corpus-derived roles of each tile id. Nothing is promoted;
no source maps / mission_assets / approved DB are touched.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
LIB = MBB / "building_block_library.json"
OUT = CLEANED / "scored_building_blocks.json"
sys.path.insert(0, str(ROOT))
import mbb_common as C  # noqa: E402

FLOOR_TYPES = {"mine_floor_base", "mine_floor_variation"}
EDGE_TYPES = {"mine_wall_left_edge", "mine_wall_right_edge"}
FACE_TYPES = {"mine_wall_forward_lower_face", "mine_wall_back_top_edge"}
CORNER_TYPES = {"mine_inner_corner", "mine_outer_corner", "mine_round_corner", "mine_angled_wall"}
BOUNDARY_TYPES = {"mine_blocked_boundary", "mine_deep_void"}
WALL_TYPES = {"mine_wall_body"} | EDGE_TYPES | FACE_TYPES


def role_grid(model, block):
    w, h = block["width"], block["height"]
    g = C.cells_to_grid(block)
    roles = {}
    fronts = {}
    for dy in range(h):
        for dx in range(w):
            st = g.get((dx, dy), {})
            roles[(dx, dy)] = C.cell_role(model, st)
            fronts[(dx, dy)] = C.front_kind(model, st)
    return w, h, roles, fronts


def _largest_void_component(w, h, roles):
    seen = set(); best = 0
    for dy in range(h):
        for dx in range(w):
            if roles[(dx, dy)] != "void" or (dx, dy) in seen:
                continue
            stack = [(dx, dy)]; seen.add((dx, dy)); n = 0
            while stack:
                cx, cy = stack.pop(); n += 1
                for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)):
                    if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and roles[(nx, ny)] == "void":
                        seen.add((nx, ny)); stack.append((nx, ny))
            best = max(best, n)
    return best


def score_block(model, block):
    w, h, roles, fronts = role_grid(model, block)
    total = w * h
    cnt = {"floor": 0, "wall": 0, "void": 0, "object": 0, "opening": 0}
    for r in roles.values():
        cnt[r] += 1
    non_void = total - cnt["void"]
    has_floor, has_wall, has_void = cnt["floor"] > 0, cnt["wall"] > 0, cnt["void"] > 0

    # column / row full-runs (for edge & corner geometry)
    full_wall_cols = [dx for dx in range(w) if all(roles[(dx, dy)] == "wall" for dy in range(h))]
    full_floor_cols = [dx for dx in range(w) if all(roles[(dx, dy)] == "floor" for dy in range(h))]
    full_wall_rows = [dy for dy in range(h) if all(roles[(dx, dy)] == "wall" for dx in range(w))]
    full_floor_rows = [dy for dy in range(h) if all(roles[(dx, dy)] == "floor" for dx in range(w))]

    def frac(n):
        return round(n / total, 3) if total else 0.0

    floorPurity = frac(cnt["floor"])
    wallPurity = round(cnt["wall"] / non_void, 3) if non_void else 0.0
    largest_void = _largest_void_component(w, h, roles)
    voidPurity = 1.0 if cnt["void"] == 0 else round(largest_void / cnt["void"], 3)

    # front pairing: overlays should sit on/above a wall cell
    front_cells = [(dx, dy) for (dx, dy), k in fronts.items() if k in ("shadow", "decor")]
    if not front_cells:
        frontPairing = 1.0
    else:
        paired = 0
        for dx, dy in front_cells:
            nb = [roles.get((dx, dy)), roles.get((dx, dy + 1)),
                  roles.get((dx, dy - 1)), roles.get((dx + 1, dy)), roles.get((dx - 1, dy))]
            if "wall" in nb:
                paired += 1
        frontPairing = round(paired / len(front_cells), 3)

    n_decor = sum(1 for k in fronts.values() if k == "decor")
    decorContam = round(1 - n_decor / total, 3)
    objectContam = round(1 - cnt["object"] / total, 3)

    # crop quality: penalise solid uninformative slabs and context-less wall fragments
    wallSpansH = bool(full_wall_rows)
    wallSpansV = bool(full_wall_cols)
    if has_wall and not has_floor and not has_void:
        cropQuality = 0.25                      # pure wall slab, no face / context shown
    elif has_wall and wallSpansH and wallSpansV:
        cropQuality = 0.4                        # wall fills frame both ways -> interior chunk
    elif has_wall and not has_floor:
        cropQuality = 0.55                       # wall + void only, no walkable context
    else:
        cropQuality = round(0.7 + 0.3 * voidPurity, 3) if has_void else 1.0

    # edge completeness: a full wall column next to a full floor column (or vice versa)
    edge_ok = any((dx in full_wall_cols) and ((dx - 1) in full_floor_cols or (dx + 1) in full_floor_cols)
                  for dx in range(w))
    if edge_ok:
        edgeCompleteness = 1.0
    elif full_wall_cols and has_floor:
        edgeCompleteness = 0.6
    elif full_wall_cols:
        edgeCompleteness = 0.4
    else:
        edgeCompleteness = 0.2 if has_wall else 0.0

    # corner completeness: a wall cell with both a horizontal and a vertical wall arm,
    # and a floor cell diagonally opposite the arms.
    corner_hits = 0
    for dy in range(h):
        for dx in range(w):
            if roles[(dx, dy)] != "wall":
                continue
            for hx in (-1, 1):
                for vy in (-1, 1):
                    if (roles.get((dx + hx, dy)) == "wall" and roles.get((dx, dy + vy)) == "wall"
                            and roles.get((dx - hx, dy - vy)) == "floor"):
                        corner_hits += 1
    cornerCompleteness = 1.0 if corner_hits >= 1 else (0.4 if has_wall and has_floor else 0.0)

    structureCompleteness = round(0.5 * (non_void / total) + 0.3 * cropQuality + 0.2 * voidPurity, 3)

    # classification confidence: does composition match the claimed blockType?
    bt = block["blockType"]
    if bt in FLOOR_TYPES:
        conf = round(floorPurity * (1 - min(1.0, wallPurity)), 3)
    elif bt == "mine_wall_body":
        conf = round(min(1.0, wallPurity * 1.1) * (0.55 + 0.45 * (has_floor or has_void)), 3)
    elif bt in FACE_TYPES:
        conf = round(0.5 * min(1.0, wallPurity * 1.1) + 0.5 * (1.0 if has_floor else 0.0), 3)
    elif bt in EDGE_TYPES:
        conf = round(edgeCompleteness, 3)
    elif bt in CORNER_TYPES:
        conf = round(cornerCompleteness, 3)
    elif bt in BOUNDARY_TYPES:
        conf = round(((cnt["void"] + cnt["wall"]) / total) * objectContam, 3)
    else:
        conf = round(structureCompleteness, 3)

    # reusable generator score: composite, hit by contamination & crop
    base = (structureCompleteness + conf + cropQuality) / 3
    reusable = round(base * objectContam * (0.7 + 0.3 * decorContam) * (0.6 + 0.4 * frontPairing), 3)

    scores = {
        "structureCompletenessScore": structureCompleteness,
        "classificationConfidence": conf,
        "floorPurityScore": floorPurity,
        "wallPurityScore": wallPurity,
        "voidPurityScore": voidPurity,
        "frontPairingScore": frontPairing,
        "edgeCompletenessScore": round(edgeCompleteness, 3),
        "cornerCompletenessScore": round(cornerCompleteness, 3),
        "cropQualityScore": round(cropQuality, 3),
        "decorationContaminationScore": decorContam,
        "objectContaminationScore": objectContam,
        "reusableGeneratorScore": reusable,
    }

    # ---- risk flags ----
    flags = []
    unexpected_void = bt not in BOUNDARY_TYPES and cnt["void"] >= max(2, total * 0.22)
    unexpected_floor = bt in BOUNDARY_TYPES and cnt["floor"] >= max(2, total * 0.33)
    if cropQuality < 0.5:
        flags.append("cropped_structure")
    if unexpected_void:
        flags.append("contains_unexpected_void")
    if unexpected_floor:
        flags.append("contains_unexpected_floor")
    if decorContam < 0.999:
        flags.append("contains_decoration")
    if objectContam < 0.999:
        flags.append("contains_light_or_object")
    # mixed unrelated structures: significant wall AND significant void AND floor, low confidence
    if has_wall and has_void and has_floor and cnt["wall"] >= 2 and cnt["void"] >= 2 and conf < 0.5:
        flags.append("mixed_unrelated_structures")
    if conf < 0.4:
        flags.append("wrong_block_type")
    cropped = "cropped_structure" in flags
    if (w <= 3 or h <= 3) and cropped and bt not in FLOOR_TYPES:
        flags.append("too_small_for_structure")
    if cropped and (w < 5 or h < 5) and bt not in FLOOR_TYPES:
        flags.append("needs_larger_context")
    major = {"cropped_structure", "contains_unexpected_void", "wrong_block_type",
             "mixed_unrelated_structures", "contains_light_or_object"}
    if reusable >= 0.62 and not (major & set(flags)):
        flags.append("good_review_candidate")

    return scores, sorted(set(flags)), {k: cnt[k] for k in cnt}


def main():
    model = C.build_model()
    lib = json.loads(LIB.read_text(encoding="utf-8"))
    out = []
    for b in lib["blocks"]:
        scores, flags, counts = score_block(model, b)
        out.append({
            "blockId": b["blockId"], "blockType": b["blockType"], "sizeClass": b["sizeClass"],
            "width": b["width"], "height": b["height"],
            "frequency": b["frequency"], "sourceMapCount": b["sourceMapCount"],
            "exampleSource": b["exampleSourceCoordinates"][:1],
            "roleCounts": counts, "scores": scores, "riskFlags": flags,
        })
    CLEANED.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "modelMapsScanned": model["mapsScanned"],
        "blockCount": len(out),
        "scoreFields": list(out[0]["scores"].keys()) if out else [],
        "scored": out,
    }, indent=2), encoding="utf-8")

    # quick aggregate for the console
    import collections
    flagct = collections.Counter(f for o in out for f in o["riskFlags"])
    good = sum(1 for o in out if "good_review_candidate" in o["riskFlags"])
    print(json.dumps({
        "scoredBlocks": len(out),
        "goodReviewCandidates": good,
        "flagCounts": dict(flagct.most_common()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
