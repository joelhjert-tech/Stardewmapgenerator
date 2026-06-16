#!/usr/bin/env python3
"""Import completed New_vanillaeditedmaps exception-review decisions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_ROOT = Path(__file__).resolve().parent
NVE_ROOT = TOOL_ROOT / "pattern_learning" / "new_vanillaeditedmaps"
EXCEPTION_ROOT = NVE_ROOT / "exception_review"
DECISION_ROOT = EXCEPTION_ROOT / "decisions"
APPROVED_ROOT = EXCEPTION_ROOT / "approved_audit_exceptions"
REJECTED_ROOT = EXCEPTION_ROOT / "rejected_patterns"
MARKER_ROOT = EXCEPTION_ROOT / "marker_only_patterns"
REPORTS_ROOT = TOOL_ROOT / "reports"

VALID_DECISIONS = {"approve_audit_exception", "mark_true_error", "marker_only_pattern", "needs_tile_approval", "unsure"}
UNSAFE_946_DECISIONS = {"approve_audit_exception", "marker_only_pattern"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def is_946_buildings_case(entry: dict[str, Any]) -> bool:
    tiles = entry.get("tileIdsByLayer") or {}
    return any(str(value).endswith(":946") for value in tiles.values()) and "Buildings" in tiles


def validate_decision(entry: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    decision = entry.get("humanDecision")
    if decision is None:
        return errors
    if decision not in VALID_DECISIONS:
        errors.append(f"{path.name}:{entry.get('caseId')}: invalid humanDecision `{decision}`.")
    if is_946_buildings_case(entry) and decision in UNSAFE_946_DECISIONS:
        errors.append(f"{path.name}:{entry.get('caseId')}: tile 946 Buildings misuse cannot become audit or marker exception.")
    return errors


def import_decisions() -> dict[str, Any]:
    for path in [DECISION_ROOT, APPROVED_ROOT, REJECTED_ROOT, MARKER_ROOT, REPORTS_ROOT]:
        path.mkdir(parents=True, exist_ok=True)
    decision_files = sorted(DECISION_ROOT.glob("*.decisions.json"))
    if not decision_files:
        report = {
            "generatedAt": now_iso(),
            "status": "waiting_for_human_review",
            "completedDecisionFiles": 0,
            "imported": {},
            "errors": [],
            "notes": ["No completed .decisions.json files were found. Templates are intentionally not imported."],
        }
        write_json(EXCEPTION_ROOT / "exception_decision_import_report.json", report)
        write_text(
            REPORTS_ROOT / "new_vanillaeditedmaps_exception_decision_import_report.md",
            "\n".join(
                [
                    "# New Vanilla-Edited Maps Exception Decision Import Report",
                    "",
                    f"- Generated: {report['generatedAt']}",
                    "- Status: waiting for human review",
                    "- Completed decision files found: 0",
                    "- Imported decisions: 0",
                    "",
                    "Copy a `.decisions.template.json` file to `.decisions.json`, fill `humanDecision`, then rerun this importer.",
                ]
            ),
        )
        print("No completed exception decision files found; waiting for human review.")
        return report

    imported: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    skipped_null = 0
    for path in decision_files:
        try:
            doc = load_json(path)
        except Exception as exc:
            errors.append(f"{path.name}: JSON parse failed: {exc}")
            continue
        for entry in doc.get("decisions", []):
            entry_errors = validate_decision(entry, path)
            if entry_errors:
                errors.extend(entry_errors)
                continue
            decision = entry.get("humanDecision")
            if decision is None:
                skipped_null += 1
                continue
            imported[decision].append({**entry, "sourceDecisionFile": str(path)})

    if errors:
        status = "failed_validation"
    else:
        status = "imported"
        if imported["approve_audit_exception"]:
            write_json(APPROVED_ROOT / "approved_audit_exceptions.imported.json", {"generatedAt": now_iso(), "entries": imported["approve_audit_exception"]})
        if imported["mark_true_error"]:
            write_json(REJECTED_ROOT / "true_errors.imported.json", {"generatedAt": now_iso(), "entries": imported["mark_true_error"]})
        if imported["marker_only_pattern"]:
            write_json(MARKER_ROOT / "marker_only_patterns.imported.json", {"generatedAt": now_iso(), "entries": imported["marker_only_pattern"]})
        if imported["needs_tile_approval"]:
            write_json(EXCEPTION_ROOT / "needs_tile_approval.imported.json", {"generatedAt": now_iso(), "entries": imported["needs_tile_approval"]})
        if imported["unsure"]:
            write_json(EXCEPTION_ROOT / "unsure.imported.json", {"generatedAt": now_iso(), "entries": imported["unsure"]})
        if imported["approve_audit_exception"]:
            proposed = {
                "generatedAt": now_iso(),
                "source": "new_vanillaeditedmaps_human_exception_review",
                "rules": [
                    {
                        "ruleId": f"human_exception_{entry['caseId']}",
                        "source": "new_vanillaeditedmaps_human_exception_review",
                        "appliesOnlyInAuditMode": True,
                        "appliesInProductionMode": False,
                        "requiredLayerStack": entry.get("layerStack"),
                        "allowedMapNames": [entry.get("mapName")],
                        "allowedTilesheets": sorted({str(value).split(":")[0] for value in (entry.get("tileIdsByLayer") or {}).values()}),
                        "tileIds": entry.get("tileIdsByLayer"),
                        "forbiddenTileIds": [946],
                        "validatorReason": entry.get("notes") or "Human-approved audit exception; production remains strict.",
                        "examples": [{"mapName": entry.get("mapName"), "x": entry.get("x"), "y": entry.get("y")}],
                    }
                    for entry in imported["approve_audit_exception"]
                ],
            }
            write_json(EXCEPTION_ROOT / "layer_grammar_exception_rules.proposed_update.json", proposed)

    counts = Counter({key: len(value) for key, value in imported.items()})
    report = {
        "generatedAt": now_iso(),
        "status": status,
        "completedDecisionFiles": len(decision_files),
        "imported": dict(counts),
        "skippedNullDecisions": skipped_null,
        "errors": errors,
        "notes": ["No tile approvals were created.", "Production rules were not changed.", "Tile 946 unsafe exceptions are rejected."],
    }
    write_json(EXCEPTION_ROOT / "exception_decision_import_report.json", report)
    write_text(
        REPORTS_ROOT / "new_vanillaeditedmaps_exception_decision_import_report.md",
        "\n".join(
            [
                "# New Vanilla-Edited Maps Exception Decision Import Report",
                "",
                f"- Generated: {report['generatedAt']}",
                f"- Status: {status}",
                f"- Completed decision files found: {len(decision_files)}",
                f"- Skipped null decisions: {skipped_null}",
                f"- Errors: {len(errors)}",
                "",
                "## Imported Counts",
                *[f"- {key}: {value}" for key, value in sorted(counts.items())],
                "",
                "## Errors",
                *(errors or ["- None."]),
            ]
        ),
    )
    if errors:
        raise SystemExit("Decision import validation failed; see report.")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import_decisions()
