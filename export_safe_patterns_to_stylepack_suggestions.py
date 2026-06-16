#!/usr/bin/env python3
"""Convert valid manual safe patterns into stylepack update suggestions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_manual_safe_patterns import PATTERN_PATH, pattern_list, validate_all


TOOL_ROOT = Path(__file__).resolve().parent
PATTERN_ROOT = TOOL_ROOT / "pattern_learning" / "manual_safe_patterns"
SUGGESTIONS_PATH = PATTERN_ROOT / "stylepack_pattern_suggestions.json"
REPORT_PATH = TOOL_ROOT / "reports" / "stylepack_pattern_suggestions.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def suggestion_for(pattern: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    targets = pattern.get("stylepackTargets") or []
    return {
        "patternId": pattern.get("patternId"),
        "patternName": pattern.get("patternName"),
        "patternType": pattern.get("patternType"),
        "category": pattern.get("category"),
        "purpose": pattern.get("purpose"),
        "profile": pattern.get("profile"),
        "stylepackTargets": targets,
        "suggestedAction": "add_as_manual_safe_pattern_reference",
        "productionStatus": validation.get("productionStatus"),
        "applyAutomatically": False,
        "reason": "Manual safe patterns inform stylepacks/generator, but this script never patches stylepacks automatically.",
        "tileRoles": [
            {
                "candidateId": tile.get("candidateId"),
                "role": tile.get("role"),
                "approvedClass": tile.get("approvedClass"),
                "approvedPurpose": tile.get("approvedPurpose"),
                "layer": tile.get("layer"),
                "collision": tile.get("collision"),
                "gridX": tile.get("gridX"),
                "gridY": tile.get("gridY"),
            }
            for tile in pattern.get("tiles", [])
        ],
        "stylepackPatchHint": {
            "manualSafePatterns": [
                {
                    "patternId": pattern.get("patternId"),
                    "purpose": pattern.get("purpose"),
                    "profile": pattern.get("profile"),
                    "productionStatus": validation.get("productionStatus"),
                }
            ]
        },
    }


def build_suggestions(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    validation = validate_all(patterns)
    validation_by_id = {item.get("patternId"): item for item in validation["results"]}
    suggestions = []
    skipped = []
    for pattern in patterns:
        result = validation_by_id.get(pattern.get("patternId"), {})
        if result.get("status") in {"valid", "needs_review"} and result.get("productionStatus") != "blocked":
            suggestions.append(suggestion_for(pattern, result))
        else:
            skipped.append(
                {
                    "patternId": pattern.get("patternId"),
                    "patternName": pattern.get("patternName"),
                    "reason": "pattern is invalid or blocked",
                    "errors": result.get("errors") or [],
                }
            )
    return {
        "generatedAt": now_iso(),
        "source": "manual_safe_patterns",
        "applyAutomatically": False,
        "suggestionCount": len(suggestions),
        "skippedCount": len(skipped),
        "suggestions": suggestions,
        "skipped": skipped,
    }


def markdown_report(doc: dict[str, Any]) -> str:
    lines = [
        "# Stylepack Pattern Suggestions",
        "",
        f"- Generated: {doc['generatedAt']}",
        f"- Suggestions: {doc['suggestionCount']}",
        f"- Skipped: {doc['skippedCount']}",
        "- Applied automatically: `false`",
        "",
        "## Suggestions",
        "",
    ]
    for item in doc["suggestions"]:
        targets = ", ".join(item.get("stylepackTargets") or []) or "none"
        lines.extend(
            [
                f"### {item.get('patternName') or item.get('patternId')}",
                "",
                f"- Pattern ID: `{item.get('patternId')}`",
                f"- Type: `{item.get('patternType')}`",
                f"- Purpose: `{item.get('purpose')}`",
                f"- Profile: `{item.get('profile')}`",
                f"- Targets: {targets}",
                f"- Production status: `{item.get('productionStatus')}`",
                f"- Tile roles: {len(item.get('tileRoles') or [])}",
                "",
            ]
        )
    if doc["skipped"]:
        lines.extend(["## Skipped", ""])
        for item in doc["skipped"]:
            lines.append(f"- `{item.get('patternId')}`: {item.get('reason')}")
    if not doc["suggestions"] and not doc["skipped"]:
        lines.append("- No manual safe patterns found.")
    return "\n".join(lines)


def main() -> int:
    patterns = pattern_list(load_json(PATTERN_PATH, {"patterns": []}))
    doc = build_suggestions(patterns)
    write_json(SUGGESTIONS_PATH, doc)
    write_text(REPORT_PATH, markdown_report(doc))
    print(f"Stylepack pattern suggestions written: {doc['suggestionCount']} suggestions, {doc['skippedCount']} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
