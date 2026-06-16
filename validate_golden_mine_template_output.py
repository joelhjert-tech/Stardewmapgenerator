#!/usr/bin/env python3
"""Validate mine prototype outputs against golden-template provenance rules."""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
DUNGEON_REVIEW = ROOT / "prototype_visual_maps" / "dungeon_review"
FIRSTGID = 1

sys.path.insert(0, str(ROOT / "prototypes"))
from golden_mine_template_resolver import (  # noqa: E402
    FRONT_WALL_OR_SHADOW_IDS,
    LADDER_IDS,
    MINE_WALL_RESTRICTED_IDS,
    UNDER_WALL_BACK_IDS,
    WALL_IDS,
)


def local_id(gid_value: int) -> Optional[int]:
    return None if gid_value <= 0 else int(gid_value) - FIRSTGID


def parse_csv_data(text: str, width: int, height: int) -> List[int]:
    cleaned = re.sub(r"\s+", "", text.strip())
    vals = [int(v) for v in cleaned.split(",") if v != ""]
    if len(vals) != width * height:
        raise ValueError(f"CSV tile count {len(vals)} != {width * height}")
    return vals


def parse_tmx(path: Path) -> dict:
    root = ET.parse(path).getroot()
    width = int(root.attrib["width"])
    height = int(root.attrib["height"])
    layers = {}
    for layer in root.findall("./layer"):
        data = layer.find("./data")
        if data is None:
            continue
        layers[layer.attrib["name"]] = parse_csv_data(data.text or "", width, height)
    props = {}
    for prop in root.findall("./properties/property"):
        props[prop.attrib.get("name", "")] = prop.attrib.get("value", "")
    return {"width": width, "height": height, "layers": layers, "properties": props}


def idx(x: int, y: int, width: int) -> int:
    return y * width + x


def get(layers: Dict[str, List[int]], layer: str, x: int, y: int, width: int, height: int) -> Optional[int]:
    if not (0 <= x < width and 0 <= y < height):
        return None
    return local_id(layers.get(layer, [0] * (width * height))[idx(x, y, width)])


def load_metadata(tmx_path: Path) -> dict:
    candidates = []
    if "template_fixed" in tmx_path.stem:
        candidates.append(tmx_path.with_name("metadata_template_fixed.json"))
    if "fixed" in tmx_path.stem:
        candidates.append(tmx_path.with_name("metadata_fixed.json"))
    candidates.extend([tmx_path.with_name("metadata.json"), tmx_path.with_name("metadata_template_fixed.json")])
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def covered_from_metadata(metadata: dict) -> Set[Tuple[str, int, int, int]]:
    covered: Set[Tuple[str, int, int, int]] = set()
    for placement in metadata.get("goldenTemplatePlacements", []):
        for cell in placement.get("cells", []):
            covered.add((cell["layer"], int(cell["x"]), int(cell["y"]), int(cell["localTileId"])))
    return covered


def neighbors4(x: int, y: int):
    yield x, y - 1
    yield x + 1, y
    yield x, y + 1
    yield x - 1, y


def is_blocked(layers: Dict[str, List[int]], x: int, y: int, width: int, height: int) -> bool:
    b = get(layers, "Buildings", x, y, width, height)
    if b is None or b in LADDER_IDS:
        return False
    return b in WALL_IDS


def is_walkable(layers: Dict[str, List[int]], x: int, y: int, width: int, height: int) -> bool:
    b = get(layers, "Buildings", x, y, width, height)
    if b in LADDER_IDS:
        return True
    back = get(layers, "Back", x, y, width, height)
    if back is None or back == 77:
        return False
    return not is_blocked(layers, x, y, width, height)


def validate_map(path: Path) -> dict:
    result = {
        "map": str(path.resolve()),
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "checks": {},
    }
    try:
        doc = parse_tmx(path)
    except Exception as exc:
        result["status"] = "FAIL"
        result["errors"].append(f"TMX parse failed: {exc}")
        return result
    metadata = load_metadata(path)
    covered = covered_from_metadata(metadata)
    placements = metadata.get("goldenTemplatePlacements", [])
    width, height, layers = doc["width"], doc["height"], doc["layers"]
    if not placements:
        result["errors"].append("No goldenTemplatePlacements metadata found.")
    for layer, data in layers.items():
        for y in range(height):
            for x in range(width):
                tid = local_id(data[idx(x, y, width)])
                if tid is None:
                    continue
                if tid == 946:
                    result["errors"].append(f"Tile 946 appears on {layer} at {x},{y}")
                if tid in MINE_WALL_RESTRICTED_IDS and (layer, x, y, tid) not in covered:
                    result["errors"].append(f"Restricted mine wall/opening tile {tid} on {layer} at {x},{y} is not covered by a golden template placement.")
                if layer == "Back" and tid == 220:
                    result["errors"].append(f"Tile 220 appears on Back at {x},{y}; golden mine templates do not allow this.")
                if layer == "Back" and tid in UNDER_WALL_BACK_IDS and (layer, x, y, tid) not in covered:
                    result["errors"].append(f"Tile {tid} appears on Back outside golden under-wall template context at {x},{y}.")
                if layer == "Front" and tid in FRONT_WALL_OR_SHADOW_IDS and (layer, x, y, tid) not in covered:
                    result["errors"].append(f"Front wall/shadow tile {tid} at {x},{y} is not golden-template covered.")
    # Ladder must be template-covered.
    ladder_cells = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if get(layers, "Buildings", x, y, width, height) in LADDER_IDS
    ]
    if not ladder_cells:
        result["errors"].append("No ladder/opening cells found.")
    for x, y in ladder_cells:
        tid = get(layers, "Buildings", x, y, width, height)
        if ("Buildings", x, y, tid) not in covered:
            result["errors"].append(f"Ladder tile {tid} at {x},{y} is not golden-template covered.")
    # Reachability from map props.
    try:
        entrance = tuple(int(v) for v in doc["properties"].get("entrance", "").split())
        exit_pos = tuple(int(v) for v in doc["properties"].get("exit", "").split())
    except Exception:
        entrance = exit_pos = None
        result["errors"].append("Missing or invalid entrance/exit properties.")
    if entrance and exit_pos:
        q = deque([entrance])
        reached = set()
        while q:
            cell = q.popleft()
            if cell in reached:
                continue
            x, y = cell
            if not (0 <= x < width and 0 <= y < height):
                continue
            if not is_walkable(layers, x, y, width, height):
                continue
            reached.add(cell)
            for nx, ny in neighbors4(x, y):
                if (nx, ny) not in reached and 0 <= nx < width and 0 <= ny < height and is_walkable(layers, nx, ny, width, height):
                    q.append((nx, ny))
        if exit_pos not in reached:
            result["errors"].append(f"Exit {exit_pos} is not reachable from entrance {entrance}.")
        result["checks"]["reachableTiles"] = len(reached)
    result["checks"]["goldenTemplatePlacements"] = len(placements)
    result["checks"]["tile946Absent"] = not any("Tile 946" in e for e in result["errors"])
    result["checks"]["restrictedTilesCovered"] = not any("not covered" in e for e in result["errors"])
    result["status"] = "FAIL" if result["errors"] else "PASS"
    return result


def default_maps() -> List[Path]:
    maps = [
        DUNGEON_REVIEW / "custom_03_golden_template_fixed" / "custom_03_golden_template_fixed.tmx",
        DUNGEON_REVIEW / "custom_03" / "custom_03_template_fixed.tmx",
        ROOT / "prototype_visual_maps" / "template_system_tests" / "dungeon_mine_template_test_visual" / "dungeon_mine_template_test_visual.tmx",
    ]
    return [p for p in maps if p.exists()]


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    args = [Path(a) for a in sys.argv[1:]]
    maps = args or default_maps()
    results = [validate_map(path) for path in maps]
    status = "PASS" if results and all(r["status"] == "PASS" for r in results) else "FAIL"
    lines = [
        "# Golden Mine Template Validation Report",
        "",
        f"- Status: {status}",
        f"- Maps checked: {len(results)}",
        "",
        "| Map | Status | Errors | Warnings | Placements |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(f"| `{Path(r['map']).name}` | {r['status']} | {len(r['errors'])} | {len(r['warnings'])} | {r['checks'].get('goldenTemplatePlacements', 0)} |")
    for r in results:
        lines += ["", f"## {Path(r['map']).name}", f"- Status: {r['status']}"]
        if r["errors"]:
            lines += ["### Errors"] + [f"- {e}" for e in r["errors"][:120]]
        if r["warnings"]:
            lines += ["### Warnings"] + [f"- {w}" for w in r["warnings"][:60]]
        if not r["errors"] and not r["warnings"]:
            lines.append("- No errors or warnings.")
    report = REPORTS / "golden_mine_template_validation_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "golden_mine_template_validation_report.json").write_text(json.dumps({"status": status, "results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "maps": len(results), "report": str(report.resolve())}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
