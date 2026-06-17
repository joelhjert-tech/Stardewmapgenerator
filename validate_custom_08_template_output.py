#!/usr/bin/env python3
"""Validate custom_08 fresh-template output."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "prototype_visual_maps" / "dungeon_review" / "custom_08_fresh_template_test"
REPORT = ROOT / "reports" / "custom_08_fresh_template_output_validation.md"
DEEP_VOID = {135}


def local_id(gid: int) -> int | None:
    return gid - 1 if gid > 0 else None


def parse_tmx(path: Path) -> tuple[dict[str, list[int]], int, int]:
    root = ET.parse(path).getroot()
    w, h = int(root.attrib["width"]), int(root.attrib["height"])
    layers = {}
    for layer in root.findall("layer"):
        data = layer.find("data")
        if data is None or data.attrib.get("encoding") != "csv":
            continue
        values = []
        for row in csv.reader(StringIO((data.text or "").strip())):
            values.extend(int(v) for v in row if v.strip())
        layers[layer.attrib["name"]] = values
    return layers, w, h


def validate(out_dir: Path = OUT) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    placements = json.loads((out_dir / "template_placement_debug.json").read_text(encoding="utf-8"))
    family_debug = json.loads((out_dir / "tile_id_family_placement_debug.json").read_text(encoding="utf-8"))
    layers, width, height = parse_tmx(out_dir / "custom_08_fresh_template_test.tmx")
    covered = set()
    family_covered = set(family_debug.get("cellFamily", {}).keys())
    for p in placements:
        if p.get("templateId") == "marker_only_fallback":
            if p.get("layerStackWritten"):
                errors.append("marker fallback wrote visual layer stack")
            continue
        if not p.get("templateId", "").startswith("fresh_") and p.get("role") != "deep_void_fill":
            errors.append(f"non-fresh template placement: {p.get('templateId')}")
        if not p.get("tileIdFamilyId"):
            errors.append(f"placement missing tile-ID family: {p.get('templateId')}")
        cells = p.get("layerStackWritten", [])
        if isinstance(cells, list):
            bld = [c for c in cells if c.get("layer") == "Buildings" and c.get("tileId") not in DEEP_VOID]
            if len(bld) == 1 and p.get("role") not in {"ladder_opening", "shaft_opening"}:
                errors.append(f"single structural Buildings cell placement outside complete family: {p.get('templateId')}")
            for c in bld:
                covered.add(f"{c['x']},{c['y']}")
    buildings = layers.get("Buildings", [])
    loose = []
    for y in range(height):
        for x in range(width):
            lid = local_id(buildings[y * width + x])
            if lid is not None and lid not in DEEP_VOID and f"{x},{y}" not in covered:
                loose.append((x, y, lid))
    if loose:
        errors.append(f"loose structural Buildings cells not covered by fresh template placement: {loose[:30]}")
    if not covered <= family_covered:
        errors.append("some template-covered cells are missing tile-ID family coverage")
    base_checks = metadata.get("validation", {}).get("checks", {})
    protected = metadata.get("protectedPathsStatus", {})
    checks = {
        "metadataParsed": True,
        "usesOnlyFreshTemplates": metadata.get("usesOnlyFreshRepeatedStructureTemplates") is True,
        "noLooseStructuralTiles": not loose,
        "completeFamilyPlacementCoverage": covered <= family_covered,
        "markerFallbackSafe": not any(p.get("templateId") == "marker_only_fallback" and p.get("layerStackWritten") for p in placements),
        "entranceExitReachable": bool(base_checks.get("entranceExitReachable")),
        "outOfBoundsSealed": bool(base_checks.get("boundarySealed")),
        "prototypeOnly": metadata.get("prototypeOnly") is True and metadata.get("productionMapOutput") is False,
        "protectedFilesUnchanged": (
            protected.get("productionMapsGenerated") is False
            and protected.get("originalMoonvillageMapsModified") is False
            and protected.get("missionAssetsModified") is False
            and protected.get("unpackedBasegameModified") is False
            and protected.get("approvedProductionDbModified") is False
        ),
    }
    for name, ok in checks.items():
        if not ok:
            errors.append(f"check failed: {name}")
    fallback_count = sum(1 for p in placements if p.get("templateId") == "marker_only_fallback")
    if fallback_count:
        warnings.append(f"marker fallback used for {fallback_count} cells")
    return {
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "issues": errors,
        "warnings": warnings,
        "metrics": {"placements": len(placements), "coveredStructuralCells": len(covered), "fallbacks": fallback_count},
    }


def write_report(result: dict[str, Any]) -> None:
    lines = ["# Custom 08 Fresh Template Output Validation", "", f"- Result: {result['status']}", "", "## Checks"]
    for k, v in result["checks"].items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines += ["", "## Metrics"] + [f"- {k}: {v}" for k, v in result["metrics"].items()]
    if result["issues"]:
        lines += ["", "## Issues"] + [f"- {e}" for e in result["issues"]]
    if result["warnings"]:
        lines += ["", "## Warnings"] + [f"- {w}" for w in result["warnings"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "custom_08_fresh_template_output_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = validate()
    write_report(result)
    print(json.dumps({"status": result["status"], "metrics": result["metrics"], "report": str(REPORT.resolve())}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
