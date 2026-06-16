#!/usr/bin/env python3
"""Validate tile grammar templates and fallback rules."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "pattern_learning" / "tile_grammar_templates" / "template_library"
FALLBACKS = ROOT / "pattern_learning" / "tile_grammar_templates" / "fallbacks" / "generator_fallback_rules.json"
REPORTS = ROOT / "reports"
VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
VALID_STATUS = {"prototype_only", "marker_only", "review_needed", "production_ready", "blocked"}
VALID_TYPES = {
    "tile_group", "grid", "layer_stack", "neighbor_mask", "edge_mask", "corner_mask",
    "expansion_matrix", "opening_template", "room_template", "corridor_template",
    "transition_template", "floor_registry_template", "placement_rule_template",
    "overlay_template", "map_patch_template", "fallback_template",
}
REQUIRED = {
    "templateId", "templateName", "templateType", "profile", "category", "sourceEvidence",
    "requiredLayers", "requiredRoles", "tile946Policy", "confidence", "productionStatus",
    "fallbackTemplateId", "validationRules",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tile_ids(obj):
    ids = []
    if isinstance(obj, dict):
        for v in obj.values():
            ids.extend(tile_ids(v))
    elif isinstance(obj, list):
        for v in obj:
            ids.extend(tile_ids(v))
    elif isinstance(obj, int):
        ids.append(obj)
    return ids


def main() -> int:
    errors = []
    warnings = []
    library_path = LIB / "tile_grammar_template_library.json"
    schema_path = LIB / "tile_grammar_template_schema.json"
    if not library_path.exists():
        errors.append(f"Missing template library: {library_path}")
        templates = []
    else:
        templates = load(library_path).get("templates", [])
    if not schema_path.exists():
        errors.append(f"Missing template schema: {schema_path}")
    else:
        try:
            load(schema_path)
        except Exception as exc:
            errors.append(f"Schema JSON parse failed: {exc}")
    fallback_ids = set()
    if FALLBACKS.exists():
        fb = load(FALLBACKS)
        fallback_ids.update(fb.get("fallbackChain", []))
    else:
        errors.append(f"Missing fallback rules: {FALLBACKS}")
    by_id = {}
    for t in templates:
        tid = t.get("templateId", "")
        if not tid:
            errors.append("Template missing templateId")
            continue
        if tid in by_id:
            errors.append(f"Duplicate templateId: {tid}")
        by_id[tid] = t
        missing = sorted(REQUIRED - set(t))
        if missing:
            errors.append(f"{tid} missing required fields: {missing}")
        if t.get("templateType") not in VALID_TYPES:
            errors.append(f"{tid} invalid templateType: {t.get('templateType')}")
        if t.get("productionStatus") not in VALID_STATUS:
            errors.append(f"{tid} invalid productionStatus: {t.get('productionStatus')}")
        for layer in t.get("requiredLayers", []):
            if layer not in VALID_LAYERS:
                errors.append(f"{tid} invalid layer: {layer}")
        fallback = t.get("fallbackTemplateId", "")
        if fallback and fallback not in by_id and fallback not in fallback_ids and fallback not in ("blocked_with_report", "marker_only_generic"):
            warnings.append(f"{tid} fallback target not yet defined before scan completion: {fallback}")
        ids = tile_ids(t.get("tileStack", {})) + tile_ids(t.get("grid", {}))
        if 946 in ids and "allowed only approved outdoor canopy" not in t.get("tile946Policy", ""):
            errors.append(f"{tid} contains tile 946 without strict policy")
        if t.get("productionStatus") == "production_ready":
            if t.get("workingModEvidence"):
                errors.append(f"{tid} is production_ready but has working-mod evidence; requires independent safety proof")
            if any("prototype" in str(e).lower() for e in t.get("riskFlags", [])):
                errors.append(f"{tid} production_ready has prototype risk flags")
        if not t.get("fallbackTemplateId") and t.get("productionStatus") != "blocked":
            errors.append(f"{tid} has no fallbackTemplateId")
    for tid, t in by_id.items():
        fallback = t.get("fallbackTemplateId", "")
        if fallback and fallback in by_id:
            continue
        if fallback and fallback not in fallback_ids and fallback not in ("blocked_with_report", "marker_only_generic"):
            warnings.append(f"{tid} fallback may resolve through runtime rule: {fallback}")
    status = "PASS" if not errors else "FAIL"
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Tile Grammar Template Validation Results",
        "",
        f"- Status: {status}",
        f"- Templates checked: {len(templates)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        "",
    ]
    if errors:
        lines += ["## Errors"] + [f"- {e}" for e in errors]
    if warnings:
        lines += ["", "## Warnings"] + [f"- {w}" for w in warnings[:100]]
    if not errors and not warnings:
        lines.append("- No errors or warnings.")
    report = REPORTS / "tile_grammar_template_validation_results.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "tile_grammar_template_validation_results.json").write_text(json.dumps({
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "templateCount": len(templates),
    }, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "templates": len(templates), "errors": len(errors), "warnings": len(warnings)}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
