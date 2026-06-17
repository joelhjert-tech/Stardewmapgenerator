#!/usr/bin/env python3
"""Validate the fresh mine/dungeon template database."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FRESH = ROOT / "pattern_learning" / "mine_dungeon_fresh_relearn"
LIBRARY = FRESH / "templates" / "mine_dungeon_fresh_template_library.json"
SCHEMA = FRESH / "templates" / "mine_dungeon_fresh_template_schema.json"
FAMILIES = FRESH / "clusters" / "mine_dungeon_tile_id_families.json"
CLUSTERS = FRESH / "clusters" / "mine_dungeon_pattern_clusters.json"
REPORT = ROOT / "reports" / "fresh_mine_dungeon_template_validation_results.md"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    lib = load(LIBRARY)
    schema = load(SCHEMA)
    families_doc = load(FAMILIES)
    clusters_doc = load(CLUSTERS)
    families = {f["familyId"]: f for f in families_doc["families"]}
    clusters = {c["clusterId"]: c for c in clusters_doc["clusters"]}
    templates = lib["templates"]

    required_sizes = {"1x3", "3x1", "3x3", "5x5", "1x5", "5x1"}
    sizes = {t["size"] for t in templates}
    if not required_sizes <= sizes:
        errors.append(f"Missing requested window template sizes: {sorted(required_sizes - sizes)}")

    for t in templates:
        tid = t.get("templateId", "<missing>")
        for field in schema["requiredTemplateFields"]:
            if field not in t:
                errors.append(f"{tid} missing required field {field}")
        family = families.get(t.get("tileIdFamilyId"))
        if not family:
            errors.append(f"{tid} references missing tile-ID family {t.get('tileIdFamilyId')}")
        if t.get("sourceClusterId") not in clusters:
            errors.append(f"{tid} references missing source cluster {t.get('sourceClusterId')}")
        if not t.get("sourceEvidence"):
            errors.append(f"{tid} has no source coordinates/evidence")
        if not t.get("layerStack"):
            errors.append(f"{tid} has no layer stack")
        if not t.get("previewPath") or not Path(t["previewPath"]).exists():
            errors.append(f"{tid} has no rendered preview")
        w, h = [int(v) for v in t["size"].split("x")]
        structural_cells = [
            c for c in t["layerStack"]
            if "Buildings" in c.get("stack", {}) and c["stack"]["Buildings"].get("localTileId") not in {77, 135}
        ]
        if w == 1 and h == 1 and structural_cells:
            errors.append(f"{tid} is a single-tile structural role list; blocked")
        if family and not family.get("requiredOrder"):
            errors.append(f"{family['familyId']} lacks requiredOrder")
        if not t.get("allowedTilesheets"):
            errors.append(f"{tid} has unknown tilesheet compatibility")
        if t.get("productionStatus") == "generator_ready" and t.get("confidence", 0) < 50:
            warnings.append(f"{tid} generator_ready confidence is low: {t.get('confidence')}")

    checks = {
        "libraryParsed": True,
        "familiesExist": bool(families),
        "clustersExist": bool(clusters),
        "templatesExist": bool(templates),
        "requestedSizesCovered": required_sizes <= sizes,
        "templatesReferenceFamilies": not any("references missing tile-ID family" in e for e in errors),
        "templatesReferenceClusters": not any("references missing source cluster" in e for e in errors),
        "templatesHaveSourceEvidence": not any("source coordinates" in e for e in errors),
        "templatesHavePreviews": not any("rendered preview" in e for e in errors),
        "noSingleTileStructuralTemplates": not any("single-tile structural" in e for e in errors),
    }
    return {
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "issues": errors,
        "warnings": warnings,
        "metrics": {"templates": len(templates), "families": len(families), "clusters": len(clusters)},
    }


def write_report(result: dict[str, Any]) -> None:
    lines = ["# Fresh Mine/Dungeon Template Validation Results", "", f"- Result: {result['status']}", "", "## Checks"]
    for k, v in result["checks"].items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines += ["", "## Metrics"] + [f"- {k}: {v}" for k, v in result["metrics"].items()]
    if result["issues"]:
        lines += ["", "## Issues"] + [f"- {e}" for e in result["issues"]]
    if result["warnings"]:
        lines += ["", "## Warnings"] + [f"- {w}" for w in result["warnings"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = validate()
    write_report(result)
    print(json.dumps({"status": result["status"], "metrics": result["metrics"], "report": str(REPORT.resolve())}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
