#!/usr/bin/env python3
"""Validate semantic dungeon layout JSON before rendering."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

from semantic_layout import SemanticLayout, load_semantic_layout_json


def _in_bounds(layout: SemanticLayout, point: tuple[int, int]) -> bool:
    x, y = point
    return 0 <= x < layout.width and 0 <= y < layout.height


def _reachable_floor(layout: SemanticLayout) -> set[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque([layout.entrance])
    while queue:
        point = queue.popleft()
        if point in seen or point not in layout.floor_mask:
            continue
        seen.add(point)
        x, y = point
        for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if neighbor not in seen and neighbor in layout.floor_mask:
                queue.append(neighbor)
    return seen


def validate_semantic_layout(layout: SemanticLayout) -> dict[str, Any]:
    issues: list[str] = []
    if layout.width <= 0 or layout.height <= 0:
        issues.append("width and height must be positive")
    if not layout.floor_mask:
        issues.append("floorMask must not be empty")

    for point in sorted(layout.floor_mask):
        if not _in_bounds(layout, point):
            issues.append(f"floorMask point out of bounds: {point}")

    if layout.entrance not in layout.floor_mask:
        issues.append(f"entrance is not inside floorMask: {layout.entrance}")
    if layout.exit not in layout.floor_mask:
        issues.append(f"exit is not inside floorMask: {layout.exit}")
    if not _in_bounds(layout, layout.entrance):
        issues.append(f"entrance out of bounds: {layout.entrance}")
    if not _in_bounds(layout, layout.exit):
        issues.append(f"exit out of bounds: {layout.exit}")

    for marker_name, points in sorted(layout.special_markers.items()):
        for point in points:
            if not _in_bounds(layout, point):
                issues.append(f"specialMarkers.{marker_name} point out of bounds: {point}")

    reachable: set[tuple[int, int]] = set()
    if layout.entrance in layout.floor_mask and layout.exit in layout.floor_mask:
        reachable = _reachable_floor(layout)
        if layout.exit not in reachable:
            issues.append(f"exit is not reachable from entrance: {layout.entrance} -> {layout.exit}")

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "mapId": layout.map_id,
        "width": layout.width,
        "height": layout.height,
        "floorCells": len(layout.floor_mask),
        "reachableFloorCells": len(reachable),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate semantic dungeon layout JSON.")
    parser.add_argument("layout_json", type=Path)
    args = parser.parse_args()
    try:
        layout = load_semantic_layout_json(args.layout_json)
        result = validate_semantic_layout(layout)
    except ValueError as exc:
        result = {"status": "FAIL", "issues": [str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
