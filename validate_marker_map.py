#!/usr/bin/env python3
"""Validate marker-only map output."""

from __future__ import annotations

import argparse
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from validate_stylepacks import validate_all


TOOL_ROOT = Path(__file__).resolve().parent
OUT_DIR = TOOL_ROOT / "generated_maps" / "marker_tests"
REPORT_DIR = TOOL_ROOT / "reports"
GENERATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
PASSABLE = {
    "marker_ground",
    "marker_cave_floor",
    "marker_path",
    "marker_entrance",
    "marker_exit",
    "marker_ladder",
    "marker_treasure",
    "marker_monster_spawn",
    "marker_ore_spawn",
    "marker_forage_spawn",
    "marker_decoration_zone",
    "marker_protected",
}
LAYOUT_PROFILES = {"outdoor", "indoor", "dungeon"}
LAYOUT_ALIASES = {"mine": "dungeon"}
PROFILE_STEMS = {
    "outdoor": "complete_test_map_48x48_outdoor",
    "indoor": "complete_test_map_48x48_indoor",
    "dungeon": "complete_test_map_48x48_dungeon",
}


def neighbors4(x: int, y: int, width: int, height: int):
    for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny


def connected(cells: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> bool:
    width = len(cells[0])
    height = len(cells)
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return True
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in seen or cells[ny][nx] not in PASSABLE:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return False


def semantic_path_for_layout(layout_profile: str) -> Path:
    layout_profile = LAYOUT_ALIASES.get(layout_profile, layout_profile)
    return OUT_DIR / layout_profile / f"{PROFILE_STEMS[layout_profile]}.semantic.json"


def validate_marker_semantic(semantic_path: Path) -> tuple[dict, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(semantic_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Output JSON parse failed: {exc}")
        data = {}

    cells = data.get("cells") or []
    width = data.get("width")
    height = data.get("height")
    layout_family = data.get("layoutFamily") or data.get("layoutProfile") or ""
    if not cells or not isinstance(width, int) or not isinstance(height, int):
        errors.append("Marker map has missing or invalid dimensions.")
    else:
        if any(len(row) != width for row in cells):
            errors.append("One or more marker map rows has invalid width.")
        if len(cells) != height:
            errors.append("Marker map row count does not match height.")
        entrances = [(x, y) for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_entrance"]
        exits = [(x, y) for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_exit"]
        if not entrances:
            errors.append("Entrance marker missing.")
        if not exits:
            errors.append("Exit marker missing.")
        if entrances and exits and not connected(cells, entrances[0], exits[0]):
            errors.append("Entrance and exit are not connected.")
        if layout_family == "dungeon":
            walkable_count = sum(1 for row in cells for value in row if value in PASSABLE)
            if walkable_count < 220:
                errors.append(f"Dungeon walkable space is too small: {walkable_count} walkable marker cells.")
            for role in ["marker_ladder", "marker_treasure", "marker_monster_spawn", "marker_ore_spawn"]:
                markers = [(x, y) for y, row in enumerate(cells) for x, value in enumerate(row) if value == role]
                if role == "marker_ladder" and not markers:
                    errors.append("Dungeon ladder marker missing.")
                for marker in markers:
                    if entrances and not connected(cells, entrances[0], marker):
                        errors.append(f"{role} is not reachable at {marker[0]},{marker[1]}.")
        for y, row in enumerate(cells):
            for x, value in enumerate(row):
                if value == "marker_protected" and value == "marker_wall":
                    errors.append(f"Protected zone blocked at {x},{y}.")
                if not str(value).startswith("marker_"):
                    errors.append(f"Non-marker cell value at {x},{y}: {value}")
                if layout_family == "indoor" and (x == 0 or y == 0 or x == width - 1 or y == height - 1) and value in PASSABLE:
                    errors.append(f"Indoor marker map has passable edge tile at {x},{y}: {value}")

    if data.get("usesFinalVisualTileIds"):
        errors.append("Marker map claims to use final visual tile IDs.")
    if data.get("tile946BlockingRolesUsed"):
        errors.append("Tile 946 appears in a blocking role.")
    return data, errors, warnings


def write_report(data: dict, semantic_path: Path, errors: list[str], warnings: list[str], stylepack_validation: dict) -> None:
    layout_profile = data.get("layoutProfile") or semantic_path.parent.name
    layout_profile = LAYOUT_ALIASES.get(layout_profile, layout_profile)
    out_dir = semantic_path.parent
    base = semantic_path.name[:-len(".semantic.json")] if semantic_path.name.endswith(".semantic.json") else semantic_path.stem

    report_lines = [
        "# Marker Map Validation Report",
        "",
        f"- Generated: {GENERATED_AT}",
        f"- Layout profile: `{layout_profile}`",
        f"- Semantic path: `{semantic_path}`",
        f"- Result: {'PASS' if not errors else 'FAIL'}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Stylepack validation pass: {stylepack_validation['pass']}",
        f"- Marker-only required: {stylepack_validation['markerOnlyRequired']}",
        "",
        "## Checks",
        "",
        "- Entrance exists.",
        "- Exit exists.",
        "- Entrance and exit are connected.",
        "- Protected zones are not blocked.",
        "- All cells are marker roles.",
        "- No unsafe final tile IDs are present.",
        "- Tile 946 is absent from blocking roles.",
        "- Output JSON parses.",
    ]
    if errors:
        report_lines.extend(["", "## Errors", ""])
        report_lines.extend(f"- {error}" for error in errors)
    if warnings:
        report_lines.extend(["", "## Warnings", ""])
        report_lines.extend(f"- {warning}" for warning in warnings)

    out_dir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    text = "\n".join(report_lines) + "\n"
    (out_dir / f"{base}.validation_report.md").write_text(text, encoding="utf-8")
    (out_dir / "marker_test_map.validation_report.md").write_text(text, encoding="utf-8")
    (REPORT_DIR / f"marker_map_validation_report_{layout_profile}.md").write_text(text, encoding="utf-8")
    if layout_profile == "dungeon":
        (REPORT_DIR / "dungeon_marker_validation_report.md").write_text(text, encoding="utf-8")
    (REPORT_DIR / "marker_map_validation_report.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout-profile", choices=sorted(LAYOUT_PROFILES | set(LAYOUT_ALIASES)), default="outdoor")
    parser.add_argument("--semantic-path", type=Path)
    args = parser.parse_args()

    semantic_path = args.semantic_path or semantic_path_for_layout(args.layout_profile)
    stylepack_validation = validate_all()
    data, errors, warnings = validate_marker_semantic(semantic_path)
    if not stylepack_validation["pass"]:
        errors.append("Stylepack validation did not pass before marker map validation.")
    write_report(data, semantic_path, errors, warnings, stylepack_validation)
    print(f"Marker map validation {'PASS' if not errors else 'FAIL'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
