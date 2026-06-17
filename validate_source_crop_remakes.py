#!/usr/bin/env python3
"""Validate exact layer-stack remakes for Mine/Dungeon Visual Canon v1."""
from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
CANON_ROOT = ROOT / "pattern_learning" / "mine_dungeon_visual_canon_v1"
REMAKE_ROOT = ROOT / "prototype_visual_maps" / "mine_visual_canon_tests"
REPORT = ROOT / "reports" / "mine_visual_canon_v1_validation_results.md"
LAYERS = ("Back", "Buildings", "Front", "AlwaysFront", "Paths")


def gid(local_id: Optional[int]) -> int:
    return 0 if local_id is None else int(local_id) + 1


def parse_tmx_layers(path: Path) -> dict[str, list[int]]:
    root = ET.parse(path).getroot()
    layers = {}
    for layer in root.findall("layer"):
        name = layer.attrib["name"]
        data = layer.find("data")
        nums = []
        if data is not None:
            for row in csv.reader(StringIO((data.text or "").strip())):
                nums.extend(int(v) for v in row if v.strip())
        layers[name] = nums
    return layers


def expected_layers(crop: dict[str, Any]) -> dict[str, list[int]]:
    width = crop["width"]
    height = crop["height"]
    layers = {layer: [0] * (width * height) for layer in LAYERS}
    half_x = width // 2
    half_y = height // 2
    for cell in crop["cells"]:
        x = cell["dx"] + half_x
        y = cell["dy"] + half_y
        idx = y * width + x
        for layer, tile in cell["stack"].items():
            layers[layer][idx] = gid(tile["localTileId"])
    return layers


def main() -> int:
    crop_doc = json.loads((CANON_ROOT / "source_crops.json").read_text(encoding="utf-8"))
    crops = {c["sourceCropId"]: c for c in crop_doc.get("crops", [])}
    issues: list[str] = []
    checked = 0
    for remake_dir in sorted(REMAKE_ROOT.glob("source_crop_remake_*")):
        meta_path = remake_dir / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        crop = crops.get(meta.get("sourceCropId"))
        if not crop:
            issues.append(f"{remake_dir.name}: missing source crop {meta.get('sourceCropId')}")
            continue
        tmx = remake_dir / f"{meta['mapId']}.tmx"
        if not tmx.exists():
            issues.append(f"{remake_dir.name}: missing TMX")
            continue
        actual = parse_tmx_layers(tmx)
        expected = expected_layers(crop)
        for layer in LAYERS:
            if actual.get(layer) != expected[layer]:
                diffs = sum(1 for a, b in zip(actual.get(layer, []), expected[layer]) if a != b)
                issues.append(f"{remake_dir.name}: {layer} mismatch ({diffs} cells)")
        for required in ("preview_clean.png", "preview_labeled.png", "source_vs_remake.png", "validation_report.md"):
            if not (remake_dir / required).exists():
                issues.append(f"{remake_dir.name}: missing {required}")
        checked += 1
    if checked < 2:
        issues.append(f"expected at least 2 exact crop remakes, found {checked}")
    status = "PASS" if not issues else "FAIL"
    existing = REPORT.read_text(encoding="utf-8") if REPORT.exists() else "# Mine/Dungeon Visual Canon v1 Validation Results\n"
    REPORT.write_text(
        existing.rstrip() + "\n\n"
        "## Source Crop Remake Exact-Match Validation\n\n"
        f"- Status: **{status}**\n"
        f"- Remakes checked: {checked}\n"
        f"- Issues: {len(issues)}\n\n"
        + ("\n".join(f"- {i}" for i in issues) if issues else "- All checked source crop remakes match exact TMX layer stacks.\n"),
        encoding="utf-8",
    )
    print(json.dumps({"status": status, "remakesChecked": checked, "issues": issues}, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
