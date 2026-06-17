#!/usr/bin/env python3
"""Validate Mine/Dungeon Visual Canon v1."""
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANON_ROOT = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1"
REPORT = ROOT / "reports" / "mine_visual_canon_v1_validation_results.md"

STRUCTURAL_ROLES = {
    "straight_wall", "lower_wall_face", "left_edge", "right_edge", "outer_corner",
    "inner_corner", "angled_wall", "ladder_opening", "shaft_opening", "wall_shadow_strip",
    "floor_to_wall_transition", "deep_void_blocked_boundary", "small_complete_room_corner",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(locked: bool = False) -> tuple[str, list[str], int, int, int]:
    issues: list[str] = []
    locked_path = CANON_ROOT / "mine_dungeon_visual_canon_v1.locked.json"
    canon_path = locked_path if locked and locked_path.exists() else CANON_ROOT / "mine_dungeon_visual_canon_v1.json"
    crops_path = CANON_ROOT / "source_crops.json"
    rules_path = CANON_ROOT / "negative_mine_template_rules.json"
    schema_path = CANON_ROOT / "mine_dungeon_visual_canon_schema.json"
    for p in (canon_path, crops_path, rules_path, schema_path):
        if not p.exists():
            issues.append(f"missing `{p}`")
    if issues:
        return "FAIL", issues, 0, 0, 0
    canon = load_json(canon_path)
    crops = load_json(crops_path)
    rules = load_json(rules_path)
    crop_by_id = {c["sourceCropId"]: c for c in crops.get("crops", [])}
    templates = canon.get("templates", [])
    if len(templates) < 10:
        issues.append("canon has fewer than 10 templates")
    if not rules.get("rules"):
        issues.append("negative rules missing")
    for t in templates:
        for field in ("templateId", "visualTheme", "sourceMap", "sourceCoordinate", "sourceCropId",
                      "role", "width", "height", "anchor", "tileIdsByLayer", "floorMask", "wallMask",
                      "voidMask", "shadowMask", "collisionMask", "openingMask", "visualStatus",
                      "generatorStatus", "locked", "previewPath"):
            if field not in t:
                issues.append(f"{t.get('templateId', '<unknown>')} missing {field}")
        if t.get("sourceCropId") not in crop_by_id:
            issues.append(f"{t.get('templateId')} references missing source crop")
        if t.get("role") in STRUCTURAL_ROLES:
            structural_cells = len(t.get("Buildings", [])) + len(t.get("Front", [])) + len(t.get("AlwaysFront", []))
            if structural_cells <= 1:
                issues.append(f"{t.get('templateId')} is structural but only has {structural_cells} structural/front cells")
        if t.get("previewPath") and not (ROOT / t["previewPath"]).exists():
            issues.append(f"{t.get('templateId')} preview missing: {t['previewPath']}")
        if t.get("locked") and t.get("visualStatus") != "Joel_approved":
            issues.append(f"{t.get('templateId')} locked without Joel_approved")
        if t.get("generatorStatus") == "generator_ready" and t.get("visualStatus") != "Joel_approved":
            issues.append(f"{t.get('templateId')} generator_ready without Joel_approved")
        if locked:
            is_locked = t.get("locked") is True
            is_rejected_or_unsure = t.get("visualStatus") in {"rejected", "needs_review", "Joel_review_needed"} or t.get("generatorStatus") in {"disabled", "marker_fallback_only"}
            if is_locked:
                if t.get("visualStatus") != "Joel_approved":
                    issues.append(f"{t.get('templateId')} locked but not Joel_approved")
                if t.get("generatorStatus") != "generator_ready":
                    issues.append(f"{t.get('templateId')} locked but not generator_ready")
                if t.get("sourceCropId") not in crop_by_id:
                    issues.append(f"{t.get('templateId')} locked without valid source crop")
                if not t.get("previewPath") or not (ROOT / t["previewPath"]).exists():
                    issues.append(f"{t.get('templateId')} locked without valid preview")
                complete_layer_count = sum(1 for layer in ("Back", "Buildings", "Front", "AlwaysFront") if t.get(layer))
                if complete_layer_count == 0 or not t.get("layerStack"):
                    issues.append(f"{t.get('templateId')} locked without complete layer data")
                structural_cells = len(t.get("Buildings", [])) + len(t.get("Front", [])) + len(t.get("AlwaysFront", []))
                if t.get("role") in STRUCTURAL_ROLES and structural_cells <= 1:
                    issues.append(f"{t.get('templateId')} locked as loose single-tile structural template")
            if is_rejected_or_unsure and t.get("generatorStatus") == "generator_ready":
                issues.append(f"{t.get('templateId')} rejected/unsure but generator_ready")
    role_count = len({t.get("role") for t in templates})
    if role_count < 8:
        issues.append(f"role coverage too thin: {role_count}")
    status = "PASS" if not issues else "FAIL"
    return status, issues, len(templates), len(crop_by_id), len(rules.get("rules", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Mine/Dungeon Visual Canon v1.")
    parser.add_argument("--locked", action="store_true", help="Validate locked derived canon, if present, with stricter approval checks.")
    args = parser.parse_args()
    status, issues, template_count, crop_count, rule_count = validate(args.locked)
    REPORT.write_text(
        "# Mine/Dungeon Visual Canon v1 Validation Results\n\n"
        f"- Mode: {'locked' if args.locked else 'base'}\n"
        f"- Status: **{status}**\n"
        f"- Templates checked: {template_count}\n"
        f"- Source crops checked: {crop_count}\n"
        f"- Negative rules checked: {rule_count}\n"
        f"- Issues: {len(issues)}\n\n"
        + ("\n".join(f"- {i}" for i in issues) if issues else "- No canon schema/safety issues found.\n"),
        encoding="utf-8",
    )
    print(json.dumps({"status": status, "mode": "locked" if args.locked else "base", "templates": template_count, "issues": issues}, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
