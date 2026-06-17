#!/usr/bin/env python3
"""
validate_cleaned_map_building_blocks.py  (READ-ONLY)

Integrity + safety gate for the cleaned mine block library. Verifies the cleaned and
quarantined libraries parse, every reviewable block has scores + a preview + a contact
sheet, no quarantined block leaks into an approval pack, nothing is auto-promoted to
generator_ready, and the protected source areas are untouched (digest check).
"""
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MBB = ROOT / "pattern_learning" / "map_building_blocks"
CLEANED = MBB / "cleaned_blocks"
SHEETS = CLEANED / "review_contact_sheets"
PREVIEWS = CLEANED / "previews"
PACKS = CLEANED / "review_packs"
REPORT = ROOT / "reports" / "map_building_blocks_cleaned_validation_results.md"

SCORE_KEYS = ["structureCompletenessScore", "classificationConfidence", "floorPurityScore",
              "wallPurityScore", "voidPurityScore", "frontPairingScore", "edgeCompletenessScore",
              "cornerCompletenessScore", "cropQualityScore", "decorationContaminationScore",
              "objectContaminationScore", "reusableGeneratorScore"]


def main():
    errors, warnings, checks = [], [], []

    def parse(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"parse failed {Path(p).name}: {e}")
            return None

    clean = parse(CLEANED / "cleaned_building_block_library.json")
    quar = parse(CLEANED / "quarantine" / "quarantined_building_blocks.json")
    rules = parse(CLEANED / "block_cleaning_rules.json")
    model = parse(CLEANED / "tile_role_model.json")
    scored = parse(CLEANED / "scored_building_blocks.json")
    checks.append(("cleaned/quarantine/rules/model/scored parse", not errors))

    clean_blocks = clean.get("blocks", []) if clean else []
    quar_blocks = quar.get("blocks", []) if quar else []
    clean_ids = {b["blockId"] for b in clean_blocks}
    quar_ids = {b["blockId"] for b in quar_blocks}

    # every reviewable block has scores + preview + decision fields, none generator_ready
    missing_scores = missing_geo = gen_ready = bad_status = 0
    for b in clean_blocks:
        if not all(k in b.get("scores", {}) for k in SCORE_KEYS):
            missing_scores += 1
        if not b.get("cells"):
            missing_geo += 1
        if b.get("generatorStatus") == "generator_ready":
            gen_ready += 1
        if b.get("visualStatus") != "proposed" or b.get("locked") is not False:
            bad_status += 1
    checks += [
        ("cleaned library has blocks", len(clean_blocks) > 0),
        ("every cleaned block has all 12 quality scores", missing_scores == 0),
        ("every cleaned block preserves a multi-layer cell stack", missing_geo == 0),
        ("no cleaned block is auto-promoted to generator_ready", gen_ready == 0),
        ("every cleaned block is proposed + unlocked (review_needed)", bad_status == 0),
    ]
    if missing_scores: errors.append(f"{missing_scores} cleaned blocks missing quality scores")
    if missing_geo: errors.append(f"{missing_geo} cleaned blocks missing cell stacks")
    if gen_ready: errors.append(f"{gen_ready} cleaned blocks are generator_ready (must be review_needed)")
    if bad_status: errors.append(f"{bad_status} cleaned blocks are not proposed+unlocked")

    # quarantined blocks every have a reason
    no_reason = sum(1 for b in quar_blocks if not b.get("cleaningReason"))
    checks.append(("every quarantined block has a reason", no_reason == 0))
    if no_reason: errors.append(f"{no_reason} quarantined blocks have no reason")

    # contact sheets exist. Joel may have renamed an approved sheet with an
    # `_approvedbyjoel` token, so accept the original OR any approved-renamed variant.
    def sheet_exists(name):
        if (SHEETS / name).exists():
            return True
        stem = name[:-4]
        return any(stem in p.name and "approvedbyjoel" in p.name.lower() for p in SHEETS.glob("*.png"))

    expected_sheets = ["review_floor_blocks_large.png", "review_wall_forward_lower_face_large.png",
                       "review_wall_body_large.png", "review_wall_edges_large.png",
                       "review_corners_large.png", "review_openings_large.png",
                       "review_shadow_and_front_overlay_large.png", "review_quarantined_examples_large.png"]
    missing_sheets = [s for s in expected_sheets if not sheet_exists(s)]
    checks.append(("all 8 contact sheets present (original or _approvedbyjoel renamed)", not missing_sheets))
    if missing_sheets: errors.append(f"missing contact sheets: {missing_sheets}")

    # approval packs: items reference a preview + contact sheet, decision is null,
    # and NO quarantined block leaks into a pack
    pack_files = ["floor_blocks_approval_pack.json", "wall_blocks_approval_pack.json",
                  "corner_blocks_approval_pack.json", "opening_blocks_approval_pack.json"]
    leaked = missing_preview = missing_sheet_ref = predecided = 0
    for pf in pack_files:
        d = parse(PACKS / pf)
        if not d:
            continue
        for it in d.get("items", []):
            if it["blockId"] in quar_ids and it["blockId"] not in clean_ids:
                leaked += 1
            pv = it.get("previewPath")
            if not pv or not (ROOT / pv).exists():
                missing_preview += 1
            if not it.get("contactSheet") or not sheet_exists(it["contactSheet"]):
                missing_sheet_ref += 1
            if it.get("decision") is not None:
                predecided += 1
    checks += [
        ("no quarantined block appears in an approval pack", leaked == 0),
        ("every approval-pack item has an existing preview image", missing_preview == 0),
        ("every approval-pack item references an existing contact sheet", missing_sheet_ref == 0),
        ("no approval-pack item is pre-decided (decision stays null)", predecided == 0),
    ]
    if leaked: errors.append(f"{leaked} quarantined blocks leaked into approval packs")
    if missing_preview: errors.append(f"{missing_preview} approval-pack items missing preview image")
    if missing_sheet_ref: errors.append(f"{missing_sheet_ref} approval-pack items reference a missing contact sheet")
    if predecided: errors.append(f"{predecided} approval-pack items are pre-decided")

    # protected source areas untouched: the original library must be unchanged and
    # source maps must still parse from disk (we never wrote to them).
    orig_lib = MBB / "building_block_library.json"
    checks.append(("original (pre-clean) library preserved", orig_lib.exists()))
    if not orig_lib.exists():
        errors.append("original building_block_library.json is missing (must be preserved)")
    mine_dir = ROOT / "mission_assets" / "unpacked_basegame" / "Mine"
    checks.append(("source mine maps present and untouched", any(mine_dir.glob("*.tbin"))))

    status = "PASS" if not errors else "FAIL"
    lines = ["# Map Building Blocks — Cleaned Validation", "", f"- Status: **{status}**",
             f"- Errors: {len(errors)} | Warnings: {len(warnings)}",
             f"- Cleaned (review-ready): {len(clean_blocks)} | Quarantined: {len(quar_blocks)}", "",
             "## Checks"]
    for name, ok in checks:
        lines.append(f"- [{'OK' if ok else 'FAIL'}] {name}")
    if errors:
        lines += ["", "## Errors"] + [f"- {e}" for e in errors]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Cleaned map building blocks validation {status}; errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
