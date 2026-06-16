#!/usr/bin/env python3
"""Validate Tiled Map Assistant style packs and project safety rules."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


TOOL_ROOT = Path(__file__).resolve().parent
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"
REPORT_DIR = TOOL_ROOT / "reports"
APPROVED_DB = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
GENERATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
COLLISION_VALUES = {
    "unknown",
    "walkable",
    "blocked",
    "water_blocked",
    "decorative_front",
    "overlay_only",
    "marker_only",
    "custom_requires_review",
}
REQUIRED_MARKER_ROLES = [
    "marker_ground",
    "marker_wall",
    "marker_wall_top",
    "marker_wall_body",
    "marker_corner",
    "marker_edge",
    "marker_transition",
    "marker_path",
    "marker_entrance",
    "marker_exit",
    "marker_decoration_zone",
    "marker_blocked",
    "marker_protected",
    "marker_water",
    "marker_overlay",
]
UNSAFE_946_PATH_TOKENS = {
    "wallBodyTiles",
    "wall_body",
    "wallBody",
    "body",
    "blockingBody",
    "Buildings",
    "wallCollision",
    "blocker",
    "collision",
    "hedge_body",
    "wall_base",
    "wall base",
}
RESTRICTED_SOURCE_TOKENS = {
    "deepwoods_custom_lake_tilesheet",
    "deepwoods_infested_outdoors_tilesheet",
    "deepwoods_exclusive_assets",
    "deepWoodsLakeTilesheet",
    "deepWoodsInfestedOutdoorsTileSheet",
}
STRUCTURAL_GROUPS = [
    "wallBodyTiles",
    "wallTopTiles",
    "cornerMatrices",
    "edgeMatrices",
    "transitionTiles",
    "pathTransitionTiles",
    "canopyOverlayTiles",
    "shadowTiles",
    "waterEdgeTiles",
]


def stylepack_files() -> list[Path]:
    return [
        path for path in sorted(STYLEPACK_DIR.glob("*.json"))
        if path.name not in {"stylepack_schema.json", "collision_schema.json"}
    ]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def path_contains_any(path: str, tokens: set[str]) -> bool:
    parts = {part for part in path.replace("\\", "/").split("/") if part}
    return bool(parts & tokens) or any(token in path for token in tokens)


def walk(value: Any, path: str = ""):
    yield path or "/", value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}/{index}")


def is_marker_ref(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("source") == "temporary_prototype_marker"
        and value.get("collision") == "marker_only"
        and (str(value.get("markerRole", "")).startswith("marker_") or value.get("gid") is not None)
    )


def tile_id_refs(pack: dict):
    for path, value in walk(pack):
        if not isinstance(value, dict):
            continue
        if "gid" in value or "localTileId" in value or "candidateId" in value:
            yield path, value


def check_schema(pack: dict, schema: dict, errors: list[dict], name: str) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(pack), key=lambda e: list(e.path)):
        errors.append({
            "file": name,
            "code": "json_schema_error",
            "path": "/" + "/".join(str(p) for p in error.path),
            "message": error.message,
        })


def validate_pack(path: Path, schema: dict) -> dict:
    name = path.name
    errors: list[dict] = []
    warnings: list[dict] = []
    try:
        pack = load_json(path)
    except Exception as exc:
        return {
            "file": name,
            "pass": False,
            "productionReady": False,
            "markerOnlyRequired": True,
            "errors": [{"file": name, "code": "json_parse_error", "path": "/", "message": str(exc)}],
            "warnings": [],
        }

    if int(pack.get("schemaVersion", 0)) < 2:
        errors.append({"file": name, "code": "schema_version_too_old", "path": "/schemaVersion", "message": "schemaVersion must be 2 or higher."})

    required = ["stylePackId", "tilesheet", "tileIdPolicy", "variantPolicy", "groups", "layerRules", "collisionRules", "densityRules", "spacingRules", "markerFallbacks"]
    for key in required:
        if key not in pack:
            errors.append({"file": name, "code": "missing_required_field", "path": f"/{key}", "message": f"Missing required field {key}."})

    try:
        check_schema(pack, schema, errors, name)
    except Exception as exc:
        errors.append({"file": name, "code": "schema_validation_runtime_error", "path": "/", "message": str(exc)})

    layer_rules = pack.get("layerRules", {})
    for key, layer in layer_rules.items():
        if layer not in VALID_LAYERS:
            errors.append({"file": name, "code": "invalid_layer_rule", "path": f"/layerRules/{key}", "message": f"Invalid Stardew layer {layer}."})

    collision_rules = pack.get("collisionRules", {})
    for key, collision in collision_rules.items():
        if collision not in COLLISION_VALUES:
            errors.append({"file": name, "code": "invalid_collision_value", "path": f"/collisionRules/{key}", "message": f"Invalid collision value {collision}."})

    for path_str, value in walk(pack):
        if isinstance(value, dict) and "collision" in value and value["collision"] not in COLLISION_VALUES:
            errors.append({"file": name, "code": "invalid_tile_collision", "path": path_str, "message": f"Invalid collision value {value['collision']}."})
        if isinstance(value, dict) and "allowedLayers" in value:
            for layer in value.get("allowedLayers") or []:
                if layer not in VALID_LAYERS:
                    errors.append({"file": name, "code": "invalid_allowed_layer", "path": path_str, "message": f"Invalid allowed layer {layer}."})

    risky_ids = {
        int(item.get("localTileId"))
        for item in pack.get("riskyTiles", [])
        if isinstance(item, dict) and item.get("localTileId") is not None
    }
    if 946 not in risky_ids:
        errors.append({"file": name, "code": "missing_tile_946_risky_policy", "path": "/riskyTiles", "message": "Tile 946 must be explicitly listed in riskyTiles."})

    quarantined_ids = {
        int(item.get("localTileId"))
        for item in pack.get("quarantinedTiles", [])
        if isinstance(item, dict) and item.get("localTileId") is not None
    }
    if 946 not in quarantined_ids:
        errors.append({"file": name, "code": "missing_tile_946_quarantine", "path": "/quarantinedTiles", "message": "Tile 946 must be explicitly listed in quarantinedTiles."})

    marker_fallbacks = pack.get("markerFallbacks", {})
    for role in REQUIRED_MARKER_ROLES:
        if role not in marker_fallbacks:
            errors.append({"file": name, "code": "missing_marker_fallback", "path": f"/markerFallbacks/{role}", "message": f"Missing marker fallback role {role}."})
        elif not is_marker_ref(marker_fallbacks[role]):
            errors.append({"file": name, "code": "invalid_marker_fallback", "path": f"/markerFallbacks/{role}", "message": f"Marker fallback {role} must be a temporary_prototype_marker marker_only tile ref."})

    for path_str, ref in tile_id_refs(pack):
        local = ref.get("localTileId")
        gid = ref.get("gid")
        if local == 946 or gid == 947:
            if path_contains_any(path_str, UNSAFE_946_PATH_TOKENS):
                errors.append({"file": name, "code": "tile_946_forbidden_role", "path": path_str, "message": "Tile 946/gid 947 is forbidden in wall/body/blocking/collision roles."})
            elif "/riskyTiles" not in path_str and "/quarantinedTiles" not in path_str:
                warnings.append({"file": name, "code": "tile_946_non_generation_reference", "path": path_str, "message": "Tile 946 appears outside active forbidden roles; keep profile-specific review."})

        source = str(ref.get("source", ""))
        if any(token.lower() in source.lower() for token in RESTRICTED_SOURCE_TOKENS):
            errors.append({"file": name, "code": "restricted_source_reference", "path": path_str, "message": f"Restricted DeepWoods source referenced: {source}."})

        if (
            "/markerTiles" in path_str
            or "/tileIdPolicy" in path_str
            or "/riskyTiles" in path_str
            or "/quarantinedTiles" in path_str
            or "/legacyGroupsBeforeSchemaV2" in path_str
            or "/legacyDensityBeforeSchemaV2" in path_str
        ):
            continue
        if is_marker_ref(ref):
            continue
        if ref.get("source") == "approved_moonvillage_database" and ref.get("candidateId") and ref.get("profileId"):
            warnings.append({"file": name, "code": "approved_db_reference_not_stream_checked", "path": path_str, "message": "Approved DB reference shape is present; deep DB stream validation is deferred until production generation is enabled."})
            continue
        errors.append({"file": name, "code": "unapproved_final_tile_id", "path": path_str, "message": "Non-marker tile refs must resolve to an approved database candidate/profile before final output."})

    groups = pack.get("groups", {})
    max_variants = int(pack.get("variantPolicy", {}).get("maxActiveVariantsPerDesignRole", 4))
    for group_name, entries in groups.items():
        if not isinstance(entries, list):
            errors.append({"file": name, "code": "group_not_array", "path": f"/groups/{group_name}", "message": "Group must be an array."})
            continue
        active_count = sum(1 for entry in entries if not isinstance(entry, dict) or entry.get("active", True))
        if active_count > max_variants:
            errors.append({"file": name, "code": "too_many_active_variants", "path": f"/groups/{group_name}", "message": f"{active_count} active variants exceeds max {max_variants}."})

    structural_marker_groups = []
    for group_name in STRUCTURAL_GROUPS:
        entries = groups.get(group_name, [])
        if not entries:
            structural_marker_groups.append(group_name)
            continue
        if all(is_marker_ref(entry) for entry in entries if isinstance(entry, dict)):
            structural_marker_groups.append(group_name)
    marker_only_required = bool(structural_marker_groups)
    production_ready = not marker_only_required and not errors
    if marker_only_required:
        warnings.append({
            "file": name,
            "code": "marker_only_required",
            "path": "/groups",
            "message": f"Structural roles are unresolved or marker-only: {', '.join(structural_marker_groups)}.",
        })

    if not APPROVED_DB.exists():
        warnings.append({"file": name, "code": "approved_db_missing", "path": str(APPROVED_DB), "message": "Approved DB path does not exist; production tile validation would be blocked."})

    return {
        "file": name,
        "stylePackId": pack.get("stylePackId", path.stem),
        "pass": not errors,
        "productionReady": production_ready,
        "markerOnlyRequired": marker_only_required,
        "errors": errors,
        "warnings": warnings,
    }


def validate_all() -> dict:
    schema = load_json(STYLEPACK_DIR / "stylepack_schema.json")
    results = [validate_pack(path, schema) for path in stylepack_files()]
    errors = [error for result in results for error in result["errors"]]
    warnings = [warning for result in results for warning in result["warnings"]]
    return {
        "generatedAt": GENERATED_AT,
        "stylepacksScanned": len(results),
        "pass": not errors,
        "productionReady": bool(results) and all(result["productionReady"] for result in results),
        "markerOnlyRequired": any(result["markerOnlyRequired"] for result in results),
        "results": results,
        "errors": errors,
        "warnings": warnings,
    }


def write_reports(summary: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "stylepack_validation_errors.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Stylepack Validation Report",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Stylepacks scanned: {summary['stylepacksScanned']}",
        f"- Validation result: {'PASS' if summary['pass'] else 'FAIL'}",
        f"- Production-ready visual output: {'YES' if summary['productionReady'] else 'NO'}",
        f"- Marker-only required: {'YES' if summary['markerOnlyRequired'] else 'NO'}",
        f"- Errors: {len(summary['errors'])}",
        f"- Warnings: {len(summary['warnings'])}",
        "",
        "## Per Stylepack",
        "",
    ]
    for result in summary["results"]:
        lines.append(f"- `{result['file']}`: {'PASS' if result['pass'] else 'FAIL'}; productionReady={result['productionReady']}; markerOnlyRequired={result['markerOnlyRequired']}; errors={len(result['errors'])}; warnings={len(result['warnings'])}")
    if summary["errors"]:
        lines.extend(["", "## Errors", ""])
        for error in summary["errors"]:
            lines.append(f"- `{error['file']}` `{error['path']}` {error['code']}: {error['message']}")
    if summary["warnings"]:
        lines.extend(["", "## Warnings", ""])
        for warning in summary["warnings"][:80]:
            lines.append(f"- `{warning['file']}` `{warning['path']}` {warning['code']}: {warning['message']}")
        if len(summary["warnings"]) > 80:
            lines.append(f"- ... {len(summary['warnings']) - 80} additional warnings omitted from markdown; see JSON.")
    lines.extend([
        "",
        "## Safety Meaning",
        "",
        "- PASS means the style packs are safe for marker-only generation.",
        "- Production visual output remains blocked while structural groups are marker-only.",
        "- Tile 946 is hard-failed if it appears in wall/body/blocking/collision roles.",
    ])
    (REPORT_DIR / "stylepack_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    summary = validate_all()
    write_reports(summary)
    if args.json_only:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Stylepack validation {'PASS' if summary['pass'] else 'FAIL'}; errors={len(summary['errors'])}; warnings={len(summary['warnings'])}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
