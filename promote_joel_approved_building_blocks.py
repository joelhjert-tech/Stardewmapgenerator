#!/usr/bin/env python3
"""
promote_joel_approved_building_blocks.py  (READ-ONLY w.r.t. sources & cleaned library)

Promotes validated Joel-approved blocks into a DERIVED library (never overwriting the
cleaned library, never touching the production DB). Only blocks that passed
validate_joel_building_block_approvals.py are promoted; invalid/ambiguous entries are left
unpromoted with a reason.

Outputs:
  - joel_approved_building_blocks_v1.json         (locked: false)
  - joel_approved_building_blocks_v1.locked.json  (locked: true)
  - reports/joel_approved_building_blocks_promotion_report.md

generatorStatus by lane:
  core_generator_safe   -> generator_ready
  decoration_or_variant -> prototype_ready
  review_needed         -> review_needed
"""
from __future__ import annotations
import json, sys, collections
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
DEC = CLEANED / "joel_sheet_approval_decisions.json"
CLEAN_LIB = CLEANED / "cleaned_building_block_library.json"
QUAR = CLEANED / "quarantine" / "quarantined_building_blocks.json"
NEG = MBB / "negative_building_block_rules.json"
VAL = CLEANED / "joel_approval_validation_results.json"
OUT = CLEANED / "joel_approved_building_blocks_v1.json"
OUT_LOCKED = CLEANED / "joel_approved_building_blocks_v1.locked.json"
REPORT = ROOT / "reports" / "joel_approved_building_blocks_promotion_report.md"

LANE_GEN_STATUS = {
    "core_generator_safe": "generator_ready",
    "decoration_or_variant": "prototype_ready",
    "review_needed": "review_needed",
}


def main():
    dec = json.loads(DEC.read_text(encoding="utf-8"))["decisions"]
    clean = {b["blockId"]: b for b in json.loads(CLEAN_LIB.read_text(encoding="utf-8"))["blocks"]}
    val = {r["blockId"]: r for r in json.loads(VAL.read_text(encoding="utf-8"))["results"]}
    neg = json.loads(NEG.read_text(encoding="utf-8"))

    promoted, unpromoted = [], []
    lane_counts = collections.Counter()
    for d in dec:
        bid = d["blockId"]
        v = val.get(bid)
        b = clean.get(bid)
        if not v or not v["valid"] or b is None:
            unpromoted.append({"blockId": bid, "blockType": d["blockType"],
                               "promotionLane": d["promotionLane"],
                               "reason": "validation failed: " + ", ".join(v["failedChecks"]) if v else "no validation result"})
            continue
        lane = d["promotionLane"]
        gen_status = LANE_GEN_STATUS[lane]
        lane_counts[lane] += 1
        promoted.append({
            "blockId": bid, "cleanedBlockId": b.get("cleanedBlockId"),
            "blockType": b["blockType"], "profile": "mine",
            "sourceCategory": "vanilla_mine", "sourceTilesheet": "mine",
            "sizeClass": b["sizeClass"], "width": b["width"], "height": b["height"],
            "anchor": b.get("anchor"), "cells": b.get("cells"),
            "floorMask": b.get("floorMask"), "wallMask": b.get("wallMask"),
            "voidMask": b.get("voidMask"), "shadowMask": b.get("shadowMask"),
            "frequency": b["frequency"], "sourceMapCount": b["sourceMapCount"],
            "exampleSource": b.get("exampleSource", []),
            "scores": b.get("scores"), "riskFlags": b.get("riskFlags"),
            "roleCounts": b.get("roleCounts"),
            "promotionLane": lane,
            "joelVisualDecision": "approved_from_contact_sheet",
            "sourceSheet": d["sourceSheet"],
            "visualStatus": "Joel_approved",
            "generatorStatus": gen_status,
            "locked": False,
            "previewPath": b.get("cleanedPreviewPath") or b.get("originalPreviewPath"),
        })

    ts = datetime.now(timezone.utc).isoformat()
    meta = {
        "generatedAt": ts, "scope": "vanilla_mine",
        "derivedFrom": "cleaned_building_block_library.json (NOT overwritten)",
        "approvalSource": "Joel _approvedbyjoel contact sheets -> deterministic mapping -> validation",
        "promotedCount": len(promoted), "unpromotedCount": len(unpromoted),
        "laneCounts": dict(lane_counts),
        "generatorStatusByLane": LANE_GEN_STATUS,
        "negativeRulesApplied": [r["id"] for r in neg.get("rules", [])],
        "note": "Production DB untouched. generator_ready here means generator-eligible mine "
                "building block, gated downstream by wall-grammar conformance + out-of-bounds checks.",
    }
    OUT.write_text(json.dumps({**meta, "blocks": promoted}, indent=2), encoding="utf-8")
    locked_blocks = [{**b, "locked": True} for b in promoted]
    OUT_LOCKED.write_text(json.dumps({**meta, "locked": True, "blocks": locked_blocks}, indent=2), encoding="utf-8")

    by = collections.Counter((b["blockType"], b["generatorStatus"]) for b in promoted)
    lines = ["# Joel-Approved Building Blocks — Promotion Report", "",
             f"- Promoted into derived library: **{len(promoted)}**",
             f"- Left unpromoted (invalid/ambiguous): **{len(unpromoted)}**",
             f"- core_generator_safe → generator_ready: **{lane_counts['core_generator_safe']}**",
             f"- decoration_or_variant → prototype_ready: **{lane_counts['decoration_or_variant']}**",
             f"- review_needed → review_needed: **{lane_counts['review_needed']}**", "",
             "Derived files (cleaned library NOT overwritten, production DB untouched):",
             "- `cleaned_blocks/joel_approved_building_blocks_v1.json` (locked: false)",
             "- `cleaned_blocks/joel_approved_building_blocks_v1.locked.json` (locked: true)", "",
             "## Promoted by type and generator status", "",
             "| blockType | generatorStatus | count |", "|---|---|--:|"]
    for (bt, gs), n in sorted(by.items()):
        lines.append(f"| {bt} | {gs} | {n} |")
    if unpromoted:
        lines += ["", "## Unpromoted", ""]
        for u in unpromoted[:50]:
            lines.append(f"- `{u['blockId']}` ({u['blockType']}) — {u['reason']}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"promoted": len(promoted), "unpromoted": len(unpromoted),
                      "laneCounts": dict(lane_counts)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
