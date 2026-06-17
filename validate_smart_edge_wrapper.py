#!/usr/bin/env python3
"""Validate registry-backed smart edge-wrapper output."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "prototype_visual_maps" / "dungeon_review" / "custom_07_advanced_edge_wrapped"
REPORTS = ROOT / "reports"
SOLID_VOID_IDS = {135}
PROTECTED_SEGMENTS = {
    "mission_assets",
    "database/tile_database_v1_human_approved.json",
    "approved_production_db",
}
REQUIRED_PATTERNS = {
    "deep_void_initialization",
    "lower_face_3_tile_extrusion",
    "shadow_below_lower_face",
    "inner_corner_L_piece",
    "outer_corner_piece",
    "straight_wall_face",
    "edge_cap",
    "fallback_marker_wall",
}
DIRS8 = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}


def local_id(gid: int) -> int | None:
    return gid - 1 if gid > 0 else None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_tmx_layers(tmx_path: Path) -> tuple[dict[str, list[int]], int, int]:
    tree = ET.parse(tmx_path)
    root = tree.getroot()
    width = int(root.attrib["width"])
    height = int(root.attrib["height"])
    layers: dict[str, list[int]] = {}
    for layer in root.findall("layer"):
        name = layer.attrib["name"]
        data = layer.find("data")
        if data is None or data.attrib.get("encoding") != "csv":
            raise ValueError(f"Layer {name} is missing CSV data")
        text = data.text or ""
        values: list[int] = []
        for row in csv.reader(StringIO(text.strip())):
            values.extend(int(v) for v in row if v.strip())
        if len(values) != width * height:
            raise ValueError(f"Layer {name} has {len(values)} cells, expected {width * height}")
        layers[name] = values
    return layers, width, height


def cells_from_template_placements(placements: list[dict[str, Any]]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for placement in placements:
        cells = placement.get("cells", [])
        if not isinstance(cells, list):
            continue
        for cell in cells:
            if cell.get("layer") == "Buildings":
                out.add((int(cell["x"]), int(cell["y"])))
    return out


def validate_output(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    metadata_path = out_dir / "metadata.json"
    edge_path = out_dir / "edge_classification_debug.json"
    placement_path = out_dir / "template_placement_debug.json"
    tmx_path = out_dir / "custom_07_advanced_edge_wrapped.tmx"

    try:
        metadata = load_json(metadata_path)
        edge_debug = load_json(edge_path)
        placements = load_json(placement_path)
        layers, width, height = parse_tmx_layers(tmx_path)
    except Exception as exc:
        return {
            "status": "FAIL",
            "checks": {"requiredFilesParsed": False},
            "issues": [f"Required output parse failed: {exc}"],
            "warnings": [],
        }

    registry_path = Path(metadata["paths"]["pattern_registry"])
    try:
        registry = load_json(registry_path)
    except Exception as exc:
        registry = {"patterns": []}
        errors.append(f"Pattern registry parse failed: {exc}")

    registry_ids = {p.get("patternId") for p in registry.get("patterns", [])}
    checks["requiredPatternRegistryEntries"] = REQUIRED_PATTERNS <= registry_ids
    if not checks["requiredPatternRegistryEntries"]:
        errors.append(f"Pattern registry missing entries: {sorted(REQUIRED_PATTERNS - registry_ids)}")

    init = metadata.get("deepVoidInitialization", {})
    checks["deepVoidInitializedBeforeCarve"] = (
        init.get("fillFullBuildingsLayerBeforeCarve") is True
        and init.get("initialCellCount") == width * height
        and any(p.get("patternId") == "deep_void_initialization" for p in placements)
    )
    if not checks["deepVoidInitializedBeforeCarve"]:
        errors.append("Deep void initialization was not recorded as a full Buildings layer pre-carve fill.")

    lower = [p for p in placements if p.get("patternId") == "lower_face_3_tile_extrusion"]
    shadows = {(p["anchor"]["x"], p["anchor"]["y"]) for p in placements if p.get("patternId") == "shadow_below_lower_face"}
    bad_lower: list[str] = []
    for placement in lower:
        ax = int(placement["anchor"]["x"])
        ay = int(placement["anchor"]["y"])
        building_cells = [c for c in placement.get("cells", []) if c.get("layer") == "Buildings"]
        coords = {(int(c["x"]), int(c["y"])) for c in building_cells}
        expected = {(ax, ay - 1), (ax, ay - 2), (ax, ay - 3)}
        if len(building_cells) != 3 or coords != expected:
            bad_lower.append(f"{ax},{ay}")
        if (ax, ay) not in shadows:
            bad_lower.append(f"{ax},{ay}:missing-shadow")
    checks["lowerFacesUseExactly3TileExtrusion"] = bool(lower) and not bad_lower
    if not checks["lowerFacesUseExactly3TileExtrusion"]:
        errors.append(f"Lower-face extrusion records are invalid: {bad_lower[:20]}")

    checks["lowerFaceShadowsOnFront"] = all(
        any(c.get("layer") == "Front" and c.get("x") == p["anchor"]["x"] and c.get("y") == p["anchor"]["y"] for c in p.get("cells", []))
        for p in placements
        if p.get("patternId") == "shadow_below_lower_face"
    )
    if not checks["lowerFaceShadowsOnFront"]:
        errors.append("One or more lower-face shadow placements is not on Front at the anchor floor cell.")

    covered = cells_from_template_placements(placements)
    buildings = layers.get("Buildings", [])
    loose: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            lid = local_id(buildings[y * width + x])
            if lid is not None and lid not in SOLID_VOID_IDS and (x, y) not in covered:
                loose.append((x, y, lid))
    checks["noLooseWallTilePlacement"] = not loose
    if loose:
        errors.append(f"Buildings structural cells not covered by template placements: {loose[:30]}")

    checks["allStructuralPlacementsRegistered"] = all(
        p.get("patternId") in registry_ids for p in placements if p.get("patternId") != "deep_void_initialization"
    )
    if not checks["allStructuralPlacementsRegistered"]:
        errors.append("One or more template placements uses a pattern not present in the registry.")

    corner_records = [r for r in edge_debug if r.get("role") in {"inner_corner", "outer_corner"}]
    checks["cornerMetadataUses8WayNeighbors"] = bool(corner_records) and all(
        set((r.get("neighbors") or {}).keys()) == DIRS8 for r in corner_records
    )
    if not checks["cornerMetadataUses8WayNeighbors"]:
        errors.append("Corner classification metadata is missing explicit 8-way neighbor maps.")

    inner_rotations = {r.get("rotation") for r in corner_records if r.get("role") == "inner_corner"}
    outer_rotations = {r.get("rotation") for r in corner_records if r.get("role") == "outer_corner"}
    checks["allFourInnerCornerRotationsPresent"] = {"SE", "SW", "NE", "NW"} <= inner_rotations
    checks["allFourOuterCornerRotationsPresent"] = {"SE", "SW", "NE", "NW"} <= outer_rotations
    if not checks["allFourInnerCornerRotationsPresent"]:
        errors.append(f"Missing inner corner rotations in output: {sorted({'SE', 'SW', 'NE', 'NW'} - inner_rotations)}")
    if not checks["allFourOuterCornerRotationsPresent"]:
        errors.append(f"Missing outer corner rotations in output: {sorted({'SE', 'SW', 'NE', 'NW'} - outer_rotations)}")

    fallbacks = [p for p in placements if p.get("patternId") == "fallback_marker_wall"]
    checks["ambiguousCornersFallbackSafely"] = all(not p.get("cells") for p in fallbacks)
    if not checks["ambiguousCornersFallbackSafely"]:
        errors.append("Fallback placements wrote visual cells; marker-only fallback must leave the deep void in place.")
    if fallbacks:
        warnings.append(f"Marker-only fallback used for {len(fallbacks)} ambiguous boundary cells.")

    base_validation = metadata.get("validation", {})
    checks["entranceExitReachable"] = bool(base_validation.get("checks", {}).get("entranceExitReachable"))
    checks["outOfBoundsSealed"] = bool(base_validation.get("checks", {}).get("boundarySealed"))
    if not checks["entranceExitReachable"]:
        errors.append("Entrance and exit/ladder are not reachable.")
    if not checks["outOfBoundsSealed"]:
        errors.append("Map has walkable out-of-bounds edge cells.")

    checks["prototypeOnlyNoProductionMap"] = metadata.get("prototypeOnly") is True and metadata.get("productionMapOutput") is False
    if not checks["prototypeOnlyNoProductionMap"]:
        errors.append("Output metadata does not mark this as prototype-only/no-production.")

    protected = metadata.get("protectedPathsStatus", {})
    checks["protectedFilesUnchanged"] = (
        protected.get("productionMapsGenerated") is False
        and protected.get("originalMoonvillageMapsModified") is False
        and protected.get("missionAssetsModified") is False
        and protected.get("unpackedBasegameModified") is False
        and protected.get("approvedProductionDbModified") is False
    )
    if not checks["protectedFilesUnchanged"]:
        errors.append("Protected path status is not clean in metadata.")

    for key, value in metadata.get("paths", {}).items():
        normalized = str(value).replace("\\", "/")
        if "/mission_assets/" in normalized or normalized.endswith("/database/tile_database_v1_human_approved.json"):
            errors.append(f"Generated path points into a protected location: {key}={value}")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "issues": errors,
        "warnings": warnings,
        "metrics": {
            "lowerFacePlacements": len(lower),
            "templatePlacements": len(placements),
            "edgeClassifications": len(edge_debug),
            "fallbacks": len(fallbacks),
            "nonVoidBuildingsCells": len([g for g in buildings if (local_id(g) is not None and local_id(g) not in SOLID_VOID_IDS)]),
        },
    }
    return result


def write_report(result: dict[str, Any], out_dir: Path = OUT_DIR) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Smart Edge Wrapper Validation",
        "",
        f"- Result: {result['status']}",
        "",
        "## Checks",
    ]
    for key, value in result.get("checks", {}).items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    lines += ["", "## Metrics"]
    for key, value in result.get("metrics", {}).items():
        lines.append(f"- {key}: {value}")
    if result.get("issues"):
        lines += ["", "## Issues"] + [f"- {issue}" for issue in result["issues"]]
    if result.get("warnings"):
        lines += ["", "## Warnings"] + [f"- {warning}" for warning in result["warnings"]]
    path = REPORTS / "custom_07_advanced_edge_wrapper_validation.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "custom_07_advanced_edge_wrapper_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", nargs="?", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    result = validate_output(args.out_dir)
    report = write_report(result, args.out_dir)
    print(json.dumps({"status": result["status"], "report": str(report.resolve()), "metrics": result.get("metrics", {})}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
