#!/usr/bin/env python3
"""Validate prototype visual mine maps against learned vanilla mine wall grammar."""
from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "prototype_visual_maps" / "dungeon_review"
REPORTS = ROOT / "reports"
FIRSTGID = 1
WALL_TOP_ON_FRONT_ONLY = {220}
UNDER_WALL_BACK = {186}
WALL_BOUNDARY_IDS = {119, 120, 121, 122, 123, 124, 157, 158}
WALL_IDS = {68, 69, 70, 71, 72, 73, 74, 75, 76, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94,
            100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 116, 117, 118, 119, 120,
            121, 122, 123, 124, 125, 126, 132, 133, 134, 141, 142, 148, 157, 158, 159, 191, 196, 207}
WOOD_SUPPORT_IDS = {20, 21, 22, 36, 37, 38}
LADDER_IDS = {67, 83, 99, 115}
STRUCTURE_SUPPORT_IDS = WALL_IDS | WOOD_SUPPORT_IDS | LADDER_IDS
BLOCKING_IDS = WALL_IDS | WOOD_SUPPORT_IDS | {238, 239}


def local_id(gid: int) -> Optional[int]:
    return None if gid <= 0 else gid - FIRSTGID


def parse_csv_data(text: str, width: int, height: int) -> List[int]:
    cleaned = re.sub(r"\s+", "", text.strip())
    vals = [int(v) for v in cleaned.split(",") if v != ""]
    if len(vals) != width * height:
        raise ValueError(f"CSV tile count {len(vals)} != {width * height}")
    return vals


def parse_tmx(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    width = int(root.attrib["width"])
    height = int(root.attrib["height"])
    layers = {}
    tilesheet_source = ""
    image = root.find(".//image")
    if image is not None:
        tilesheet_source = image.attrib.get("source", "")
    props = {}
    for prop in root.findall("./properties/property"):
        props[prop.attrib.get("name", "")] = prop.attrib.get("value", "")
    for layer in root.findall("./layer"):
        lname = layer.attrib["name"]
        data = layer.find("./data")
        if data is None:
            continue
        layers[lname] = parse_csv_data(data.text or "", width, height)
    return {"width": width, "height": height, "layers": layers, "tilesheetSource": tilesheet_source, "properties": props}


def idx(x: int, y: int, width: int) -> int:
    return y * width + x


def get(layers: Dict[str, List[int]], layer: str, x: int, y: int, width: int, height: int) -> Optional[int]:
    if not (0 <= x < width and 0 <= y < height):
        return None
    return local_id(layers.get(layer, [0] * (width * height))[idx(x, y, width)])


def near_buildings_wall(layers: Dict[str, List[int]], x: int, y: int, width: int, height: int, radius: int = 1) -> bool:
    for yy in range(y - radius, y + radius + 1):
        for xx in range(x - radius, x + radius + 1):
            tid = get(layers, "Buildings", xx, yy, width, height)
            if tid in STRUCTURE_SUPPORT_IDS:
                return True
    return False


def neighbors4(x: int, y: int):
    yield x, y - 1
    yield x + 1, y
    yield x, y + 1
    yield x - 1, y


def is_blocked(layers: Dict[str, List[int]], x: int, y: int, width: int, height: int) -> bool:
    b = get(layers, "Buildings", x, y, width, height)
    if b is None or b in LADDER_IDS:
        return False
    return b in BLOCKING_IDS


def is_walkable_visual(layers: Dict[str, List[int]], x: int, y: int, width: int, height: int) -> bool:
    b = get(layers, "Buildings", x, y, width, height)
    if b in LADDER_IDS:
        return True
    back = get(layers, "Back", x, y, width, height)
    return back is not None and back != 77 and not is_blocked(layers, x, y, width, height)


def validate_map(path: Path) -> dict:
    result = {"map": str(path.resolve()), "status": "PASS", "errors": [], "warnings": [], "checks": {}}
    try:
        doc = parse_tmx(path)
    except Exception as exc:
        result["status"] = "FAIL"
        result["errors"].append(f"TMX parse failed: {exc}")
        return result
    width, height, layers = doc["width"], doc["height"], doc["layers"]
    if "mine.png" not in doc["tilesheetSource"]:
        result["errors"].append(f"Unexpected tilesheet source: {doc['tilesheetSource']}")
    # Tile layer checks.
    for lname, data in layers.items():
        for y in range(height):
            for x in range(width):
                tid = local_id(data[idx(x, y, width)])
                if tid is None:
                    continue
                if tid == 946:
                    result["errors"].append(f"Tile 946 appears on {lname} at {x},{y}")
                if lname == "Back" and tid in WALL_TOP_ON_FRONT_ONLY:
                    result["errors"].append(f"Tile {tid} appears on Back at {x},{y}; expected Front only")
                if lname == "Back" and tid in UNDER_WALL_BACK and not near_buildings_wall(layers, x, y, width, height, 1):
                    result["errors"].append(f"Tile {tid} appears on Back away from wall boundary at {x},{y}")
                if lname == "Buildings" and tid in WALL_BOUNDARY_IDS and not near_buildings_wall(layers, x, y, width, height, 1):
                    result["warnings"].append(f"Boundary wall tile {tid} has weak wall neighborhood at {x},{y}")
    # Ladder stack checks.
    ladder_positions = []
    for y in range(height):
        for x in range(width):
            b = get(layers, "Buildings", x, y, width, height)
            if b in LADDER_IDS:
                ladder_positions.append((x, y, b))
    by_x = {}
    for x, y, b in ladder_positions:
        by_x.setdefault(x, []).append((y, b))
    valid_ladder = False
    for x, items in by_x.items():
        ys = sorted(y for y, _ in items)
        if len(ys) >= 3 and max(ys) - min(ys) <= 4:
            if near_buildings_wall(layers, x - 1, max(ys), width, height, 1) or near_buildings_wall(layers, x + 1, max(ys), width, height, 1):
                valid_ladder = True
    if not valid_ladder:
        result["errors"].append("No valid ladder stack anchored into a wall opening was found.")
    # Reachability.
    entrance_prop = doc["properties"].get("entrance", "")
    exit_prop = doc["properties"].get("exit", "")
    try:
        entrance = tuple(int(v) for v in entrance_prop.split())
        exit_pos = tuple(int(v) for v in exit_prop.split())
    except Exception:
        entrance = exit_pos = None
        result["errors"].append("Missing or invalid entrance/exit map properties.")
    if entrance and exit_pos:
        reachable = set()
        q = deque([entrance])
        while q:
            cell = q.popleft()
            if cell in reachable:
                continue
            x, y = cell
            if not (0 <= x < width and 0 <= y < height):
                continue
            if not is_walkable_visual(layers, x, y, width, height):
                continue
            reachable.add(cell)
            for nx, ny in neighbors4(x, y):
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in reachable and is_walkable_visual(layers, nx, ny, width, height):
                    q.append((nx, ny))
        if exit_pos not in reachable:
            result["errors"].append(f"Exit {exit_pos} is not reachable from entrance {entrance}.")
        result["checks"]["reachableTiles"] = len(reachable)
    result["checks"]["tile946Absent"] = not any("Tile 946" in e for e in result["errors"])
    result["checks"]["tile220AbsentFromBack"] = not any("Tile 220 appears on Back" in e for e in result["errors"])
    result["checks"]["tile186Contextual"] = not any("Tile 186 appears on Back away" in e for e in result["errors"])
    result["checks"]["validLadderOpening"] = valid_ladder
    result["status"] = "FAIL" if result["errors"] else "PASS"
    return result


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    maps = sorted(OUT_ROOT.glob("*/*_fixed.tmx"))
    results = [validate_map(path) for path in maps]
    lines = [
        "# Mine Visual Pattern Validation Report",
        "",
        "| Map | Status | Errors | Warnings |",
        "|---|---:|---:|---:|",
    ]
    for r in results:
        lines.append(f"| `{Path(r['map']).name}` | {r['status']} | {len(r['errors'])} | {len(r['warnings'])} |")
    for r in results:
        lines += ["", f"## {Path(r['map']).name}", f"- Status: {r['status']}"]
        if r["errors"]:
            lines.append("### Errors")
            lines += [f"- {e}" for e in r["errors"][:80]]
        if r["warnings"]:
            lines.append("### Warnings")
            lines += [f"- {w}" for w in r["warnings"][:40]]
        if not r["errors"] and not r["warnings"]:
            lines.append("- No errors or warnings.")
    report = REPORTS / "mine_visual_pattern_validation_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "mine_visual_pattern_validation_report.json").write_text(json.dumps({
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "results": results,
    }, indent=2), encoding="utf-8")
    overall = "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"
    print(json.dumps({"status": overall, "maps": len(results), "report": str(report.resolve())}, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
