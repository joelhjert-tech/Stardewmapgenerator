#!/usr/bin/env python3
"""Import Joel decisions into a derived locked Mine/Dungeon Visual Canon file.

This intentionally does not overwrite mine_dungeon_visual_canon_v1.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CANON_ROOT = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1"
DEFAULT_DECISIONS = CANON_ROOT / "joel_review_pack" / "mine_visual_canon_v1_decisions.json"
SOURCE_CANON = CANON_ROOT / "mine_dungeon_visual_canon_v1.json"
SOURCE_CROPS = CANON_ROOT / "source_crops.json"
LOCKED_CANON = CANON_ROOT / "mine_dungeon_visual_canon_v1.locked.json"
REPORT = ROOT / "reports" / "mine_visual_canon_decision_import_report.md"

STRUCTURAL_ROLES = {
    "straight_wall", "lower_wall_face", "left_edge", "right_edge", "outer_corner",
    "inner_corner", "angled_wall", "ladder_opening", "shaft_opening", "wall_shadow_strip",
    "floor_to_wall_transition", "deep_void_blocked_boundary", "small_complete_room_corner",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def can_lock(template: dict[str, Any], crop_ids: set[str]) -> tuple[bool, str]:
    if template.get("sourceCropId") not in crop_ids:
        return False, "missing source crop"
    preview = template.get("previewPath")
    if not preview or not (ROOT / preview).exists():
        return False, "missing preview"
    structural_cells = len(template.get("Buildings", [])) + len(template.get("Front", [])) + len(template.get("AlwaysFront", []))
    if template.get("role") in STRUCTURAL_ROLES and structural_cells <= 1:
        return False, "loose single-tile structural template"
    if not template.get("layerStack"):
        return False, "missing complete layer stack"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Joel visual canon decisions into a derived locked canon.")
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.decisions.exists():
        print(json.dumps({"status": "blocked", "reason": f"decisions file not found: {args.decisions}"}, indent=2))
        return 2

    canon = load(SOURCE_CANON)
    crops = load(SOURCE_CROPS)
    decisions_doc = load(args.decisions)
    crop_ids = {c["sourceCropId"] for c in crops.get("crops", [])}
    by_id = {t["templateId"]: t for t in canon.get("templates", [])}
    applied = []
    issues = []

    for decision in decisions_doc.get("decisions", []):
        tid = decision.get("templateId", "")
        template = by_id.get(tid)
        if not template:
            issues.append(f"unknown templateId `{tid}`")
            continue
        d = str(decision.get("decision", "")).strip().lower()
        if d == "approve":
            ok, reason = can_lock(template, crop_ids)
            if not ok:
                issues.append(f"{tid}: cannot approve/lock: {reason}")
                continue
            template["visualStatus"] = "Joel_approved"
            template["generatorStatus"] = "generator_ready"
            template["locked"] = True
            template["approvedBy"] = decisions_doc.get("reviewer", "Joel")
            template["approvedAt"] = now_iso()
        elif d == "reject":
            template["visualStatus"] = "rejected"
            template["generatorStatus"] = "disabled"
            template["locked"] = False
        elif d == "unsure":
            template["visualStatus"] = "needs_review"
            template["generatorStatus"] = "marker_fallback_only"
            template["locked"] = False
        else:
            issues.append(f"{tid}: invalid decision `{decision.get('decision')}`")
            continue
        template["reviewNotes"] = decision.get("notes", "")
        applied.append({"templateId": tid, "decision": d})

    canon["derivedFrom"] = str(SOURCE_CANON.resolve())
    canon["decisionSource"] = str(args.decisions.resolve())
    canon["decisionImportedAt"] = now_iso()
    canon["lockedTemplateCount"] = sum(1 for t in canon.get("templates", []) if t.get("locked") is True)

    if not args.dry_run and not issues:
        LOCKED_CANON.write_text(json.dumps(canon, indent=2), encoding="utf-8")

    REPORT.write_text(
        "# Mine Visual Canon Decision Import Report\n\n"
        f"- Status: {'DRY_RUN' if args.dry_run else ('BLOCKED' if issues else 'IMPORTED')}\n"
        f"- Decisions file: `{args.decisions}`\n"
        f"- Output locked canon: `{LOCKED_CANON}`\n"
        f"- Applied decisions: {len(applied)}\n"
        f"- Issues: {len(issues)}\n\n"
        + ("\n".join(f"- {i}" for i in issues) if issues else "- No import issues.\n"),
        encoding="utf-8",
    )
    print(json.dumps({"status": "blocked" if issues else ("dry_run" if args.dry_run else "imported"), "applied": len(applied), "issues": issues}, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
