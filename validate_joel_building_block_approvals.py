#!/usr/bin/env python3
"""
validate_joel_building_block_approvals.py  (READ-ONLY)

Validates every Joel-approved block decision before promotion. Writes a machine-readable
per-block result (consumed by promote_joel_approved_building_blocks.py) and a report. A
block that fails any check is NOT promoted; the failure is reported.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
DEC = CLEANED / "joel_sheet_approval_decisions.json"
INV = CLEANED / "joel_approved_contact_sheet_inventory.json"
CLEAN_LIB = CLEANED / "cleaned_building_block_library.json"
QUAR = CLEANED / "quarantine" / "quarantined_building_blocks.json"
NEG = MBB / "negative_building_block_rules.json"
RESULTS = CLEANED / "joel_approval_validation_results.json"
REPORT = ROOT / "reports" / "joel_building_block_approval_validation.md"

SCORE_KEYS = ["structureCompletenessScore", "classificationConfidence", "reusableGeneratorScore",
              "cropQualityScore", "objectContaminationScore", "decorationContaminationScore"]
STRUCTURAL = {"mine_wall_forward_lower_face", "mine_wall_back_top_edge", "mine_wall_body",
              "mine_wall_left_edge", "mine_wall_right_edge", "mine_inner_corner",
              "mine_outer_corner", "mine_angled_wall", "mine_blocked_boundary"}
CONTAM_FLAGS = {"contains_light_or_object", "contains_decoration"}
CORE_DISQUALIFYING = CONTAM_FLAGS | {"cropped_structure", "wrong_block_type",
                                     "mixed_unrelated_structures", "contains_unexpected_void"}
VOID = {77, 135}


def main():
    dec = json.loads(DEC.read_text(encoding="utf-8"))["decisions"]
    clean = json.loads(CLEAN_LIB.read_text(encoding="utf-8"))["blocks"]
    quar = json.loads(QUAR.read_text(encoding="utf-8"))["blocks"]
    inv = json.loads(INV.read_text(encoding="utf-8"))
    clean_idx = {b["blockId"]: b for b in clean}
    quar_ids = {b["blockId"] for b in quar}
    mapped_ids = {ref["blockId"] for sh in inv["sheets"] if sh["promotionEligible"] for ref in sh["blockIds"]}

    results = []
    for d in dec:
        bid = d["blockId"]
        lane = d["promotionLane"]
        b = clean_idx.get(bid)
        checks = {}
        checks["exists_in_cleaned_library"] = b is not None
        checks["appears_in_approved_sheet_mapping"] = bid in mapped_ids
        checks["not_quarantined"] = bid not in quar_ids
        if b:
            cells = b.get("cells") or []
            scores = b.get("scores", {})
            src = (b.get("exampleSource") or [{}])[0]
            real = any(int(t) not in VOID for c in cells for t in c["stack"].values())
            checks["has_preview"] = bool(b.get("originalPreviewPath")) and \
                (ROOT / b["originalPreviewPath"]).exists() if b.get("originalPreviewPath") else False
            checks["has_source_map_and_coordinate"] = bool(src.get("map")) and src.get("x") is not None
            checks["has_complete_layer_data"] = bool(cells) and all("stack" in c and c["stack"] for c in cells)
            checks["has_block_type"] = bool(b.get("blockType"))
            checks["has_quality_scores"] = all(k in scores for k in SCORE_KEYS)
            checks["not_loose_single_tile_structural"] = not (b["blockType"] in STRUCTURAL and len(cells) < 2)
            # negative rules (machine-checkable subset)
            checks["neg_void_not_art"] = real
            checks["neg_not_singleton"] = b.get("frequency", 0) >= 4 and b.get("sourceMapCount", 0) >= 3
            front_only = bool(b.get("shadowMask")) and not b.get("wallMask") and not b.get("floorMask")
            checks["neg_front_overlay_has_base"] = not front_only
            flags = set(b.get("riskFlags", []))
            rc = b.get("roleCounts", {})
            if lane == "core_generator_safe":
                checks["core_no_contamination"] = not (CORE_DISQUALIFYING & flags) and rc.get("object", 0) == 0
            if lane == "decoration_or_variant":
                # must not be proposed as core layout (lane already separates it)
                checks["decoration_not_core"] = (lane != "core_generator_safe")
            if rc.get("opening", 0) > 0 or lane == "review_needed":
                # openings must not be generator_ready without socket evidence
                checks["opening_not_generator_ready"] = (d["proposedGeneratorStatus"] != "generator_ready")
        else:
            for k in ("has_preview", "has_source_map_and_coordinate", "has_complete_layer_data",
                      "has_block_type", "has_quality_scores", "not_loose_single_tile_structural"):
                checks[k] = False

        # core lane additionally requires not_quarantined
        passed = all(checks.values())
        # a quarantined block may still be a valid review_needed entry, but never core
        if lane == "core_generator_safe" and not checks.get("not_quarantined", False):
            passed = False
        results.append({
            "blockId": bid, "cleanedBlockId": d.get("cleanedBlockId"),
            "blockType": d["blockType"], "promotionLane": lane,
            "proposedGeneratorStatus": d["proposedGeneratorStatus"],
            "checks": checks, "valid": passed,
            "failedChecks": [k for k, v in checks.items() if not v],
        })

    n_pass = sum(1 for r in results if r["valid"])
    by_lane = {}
    for r in results:
        by_lane.setdefault(r["promotionLane"], {"pass": 0, "fail": 0})
        by_lane[r["promotionLane"]]["pass" if r["valid"] else "fail"] += 1

    ts = datetime.now(timezone.utc).isoformat()
    RESULTS.write_text(json.dumps({
        "generatedAt": ts, "blockCount": len(results),
        "validCount": n_pass, "invalidCount": len(results) - n_pass,
        "byLane": by_lane, "results": results,
    }, indent=2), encoding="utf-8")

    status = "PASS" if n_pass == len(results) else "PARTIAL"
    lines = ["# Joel Building Block Approval — Validation", "",
             f"- Decisions validated: **{len(results)}**",
             f"- Valid (promotable): **{n_pass}** | Invalid: **{len(results) - n_pass}**",
             f"- Overall: **{status}** (invalid entries are simply left unpromoted)", "",
             "## By lane", "", "| lane | pass | fail |", "|---|--:|--:|"]
    for lane, c in sorted(by_lane.items()):
        lines.append(f"| {lane} | {c['pass']} | {c['fail']} |")
    fails = [r for r in results if not r["valid"]]
    if fails:
        lines += ["", "## Invalid entries (not promoted)", ""]
        for r in fails[:60]:
            lines.append(f"- `{r['blockId']}` ({r['blockType']}, {r['promotionLane']}) — failed: {', '.join(r['failedChecks'])}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Joel approval validation: {n_pass}/{len(results)} valid; byLane={by_lane}")
    # exit 0 even with invalid entries: invalids are excluded from promotion, not a hard failure
    return 0


if __name__ == "__main__":
    sys.exit(main())
