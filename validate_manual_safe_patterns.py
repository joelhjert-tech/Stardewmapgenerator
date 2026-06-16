#!/usr/bin/env python3
"""Validate manually reviewed reusable safe tile patterns."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import approval_validation_utils as approval_utils


TOOL_ROOT = Path(__file__).resolve().parent
PATTERN_ROOT = TOOL_ROOT / "pattern_learning" / "manual_safe_patterns"
PATTERN_PATH = PATTERN_ROOT / "manual_safe_patterns.json"
REPORT_PATH = TOOL_ROOT / "reports" / "manual_safe_pattern_validation_report.md"
CLASS_SCHEMA = TOOL_ROOT / "classification" / "tile_class_schema.json"
COLLISION_SCHEMA = TOOL_ROOT / "stylepacks" / "collision_schema.json"
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"

VALID_PATTERN_TYPES = {"tile_group", "grid", "layer_stack", "neighbor_mask", "stylepack_pattern"}
VALID_CATEGORIES = {"Ground", "Path", "Transition", "Water", "Wall", "Hedge", "Canopy", "Shadow", "Interior", "Dungeon", "Decoration", "Technical", "Custom"}
VALID_PROFILES = {"outdoor", "indoor", "dungeon", "mine", "any"}
VALID_ROLES = {"base", "variation", "edge", "corner", "inner_corner", "outer_corner", "top", "body", "side", "cap", "center", "shadow", "overlay", "transition", "entrance", "exit", "decoration", "marker"}
VALID_LAYERS = {"Back", "Buildings", "Front", "AlwaysFront", "Paths"}
VALID_EDGES = {"N", "S", "E", "W"}
VALID_CORNERS = {"NE", "NW", "SE", "SW"}
VALID_TRANSITIONS = {"none", "edge", "inner_corner", "outer_corner", "mixed", "center", "cap", "end", "junction", None}
BLOCKING_COLLISIONS = {"blocked", "water_blocked"}
TILE_946_ALLOWED_CLASSES = {"canopy_overlay", "tree_canopy"}
TILE_946_ALLOWED_PURPOSES = {"tree_canopy_center", "canopy_center"}
TILE_946_ALLOWED_SHEET_TOKENS = {
    "spring_outdoorstilesheet",
    "fall_outdoorstilesheet",
    "winter_outdoorstilesheet",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def pattern_list(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [item for item in doc if isinstance(item, dict)]
    if isinstance(doc, dict):
        return [item for item in doc.get("patterns", []) if isinstance(item, dict)]
    return []


def load_class_names() -> set[str]:
    doc = load_json(CLASS_SCHEMA, {})
    return set(doc.keys()) if isinstance(doc, dict) else set()


def load_collision_values() -> set[str]:
    doc = load_json(COLLISION_SCHEMA, {})
    values = doc.get("enum") if isinstance(doc, dict) else None
    return set(values or ["walkable", "blocked", "water_blocked", "decorative_front", "overlay_only", "marker_only", "custom_requires_review"])


def load_stylepack_ids() -> set[str]:
    ids: set[str] = set()
    if not STYLEPACK_DIR.exists():
        return ids
    for path in STYLEPACK_DIR.glob("*.json"):
        if path.name in {"stylepack_schema.json", "collision_schema.json"}:
            continue
        ids.add(path.stem)
        try:
            doc = load_json(path, {})
            for key in ("stylepackId", "id", "name"):
                if isinstance(doc, dict) and doc.get(key):
                    ids.add(str(doc[key]))
        except Exception:
            continue
    return ids


def normalize_sheet_text(tile: dict[str, Any], candidate: dict[str, Any] | None) -> str:
    pieces = [
        tile.get("sourceTilesheet"),
        candidate.get("sourceTilesheet") if candidate else None,
        candidate.get("tilesheetName") if candidate else None,
        candidate.get("imageName") if candidate else None,
        candidate.get("copiedImagePath") if candidate else None,
    ]
    return " ".join(str(piece or "").replace("\\", "/").lower() for piece in pieces)


def local_tile_id(tile: dict[str, Any], candidate: dict[str, Any] | None) -> int | None:
    value = tile.get("localTileId")
    if value is None and candidate:
        value = candidate.get("localTileId")
    try:
        return int(value)
    except Exception:
        return None


def tile_946_errors(tile: dict[str, Any], candidate: dict[str, Any] | None) -> list[str]:
    if local_tile_id(tile, candidate) != 946:
        return []
    errors: list[str] = []
    approved_class = str(tile.get("approvedClass") or "")
    purpose = str(tile.get("approvedPurpose") or "")
    layer = str(tile.get("layer") or "")
    collision = str(tile.get("collision") or "")
    role = str(tile.get("role") or "")
    sheet_text = normalize_sheet_text(tile, candidate)
    if approved_class not in TILE_946_ALLOWED_CLASSES:
        errors.append("tile 946 may only be used in safe patterns as canopy_overlay/tree_canopy.")
    if purpose not in TILE_946_ALLOWED_PURPOSES:
        errors.append("tile 946 safe-pattern purpose must be tree_canopy_center or canopy_center.")
    if layer != "AlwaysFront":
        errors.append("tile 946 safe-pattern layer must be AlwaysFront.")
    if collision != "overlay_only":
        errors.append("tile 946 safe-pattern collision must be overlay_only.")
    if role in {"body", "side"} or "wall" in purpose or "hedge_body" in purpose:
        errors.append("tile 946 cannot be used as wall/body/hedge body.")
    if not any(token in sheet_text for token in TILE_946_ALLOWED_SHEET_TOKENS):
        errors.append("tile 946 safe-pattern sheet must be spring/fall/winter outdoorsTileSheet context.")
    return errors


def approved_entry_for_tile(tile: dict[str, Any], candidate: dict[str, Any] | None, approvals: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ids = [tile.get("candidateId")]
    if candidate:
        ids.extend([candidate.get("candidateId"), candidate.get("pathBaseCandidateId"), candidate.get("structuralCandidateId")])
    for cid in ids:
        if cid and str(cid) in approvals:
            return approvals[str(cid)]
    return None


def stronger_metadata_errors(tile: dict[str, Any], entry: dict[str, Any] | None) -> list[str]:
    if not approval_utils.db_entry_is_stronger(entry):
        return []
    errors = []
    profile = {
        "approvedClass": tile.get("approvedClass"),
        "approvedPurpose": tile.get("approvedPurpose"),
        "allowedLayers": [tile.get("layer")] if tile.get("layer") else [],
        "collision": tile.get("collision"),
    }
    if not approval_utils.same_approval(profile, entry):
        errors.extend(approval_utils.conflict_with_approval(profile, entry))
    return errors


def validate_tile(
    tile: dict[str, Any],
    index: int,
    pattern: dict[str, Any],
    *,
    class_names: set[str],
    collision_values: set[str],
    candidates: dict[str, dict[str, Any]],
    approvals: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], bool]:
    label = f"tile #{index + 1} `{tile.get('candidateId')}`"
    errors: list[str] = []
    warnings: list[str] = []
    candidate = candidates.get(str(tile.get("candidateId") or ""))
    if not tile.get("candidateId"):
        errors.append(f"{label}: candidateId is required.")
    elif not candidate:
        errors.append(f"{label}: candidateId does not exist in candidate indexes.")
    if tile.get("role") not in VALID_ROLES:
        errors.append(f"{label}: invalid or missing role `{tile.get('role')}`.")
    if tile.get("approvedClass") not in class_names:
        errors.append(f"{label}: approvedClass `{tile.get('approvedClass')}` is not in tile_class_schema.json.")
    if not tile.get("approvedPurpose"):
        errors.append(f"{label}: approvedPurpose is required.")
    if tile.get("layer") not in VALID_LAYERS:
        errors.append(f"{label}: invalid layer `{tile.get('layer')}`.")
    if tile.get("collision") not in collision_values:
        errors.append(f"{label}: invalid collision `{tile.get('collision')}`.")
    if tile.get("layer") == "AlwaysFront" and tile.get("collision") in BLOCKING_COLLISIONS:
        errors.append(f"{label}: AlwaysFront tile cannot carry blocking collision.")
    if tile.get("layer") == "Buildings" and tile.get("collision") == "walkable":
        warnings.append(f"{label}: Buildings layer with walkable collision is unusual.")
    if tile.get("layer") == "Paths" and tile.get("approvedClass") not in {"marker_only", "warp_marker", "npc_marker", "event_marker"}:
        warnings.append(f"{label}: Paths layer is technical; confirm this is not a visual tile.")
    for value in tile.get("edgeMask") or []:
        if value not in VALID_EDGES:
            errors.append(f"{label}: invalid edgeMask value `{value}`.")
    for value in tile.get("cornerMask") or []:
        if value not in VALID_CORNERS:
            errors.append(f"{label}: invalid cornerMask value `{value}`.")
    if tile.get("transitionType") not in VALID_TRANSITIONS:
        errors.append(f"{label}: invalid transitionType `{tile.get('transitionType')}`.")
    errors.extend(f"{label}: {error}" for error in tile_946_errors(tile, candidate))
    entry = approved_entry_for_tile(tile, candidate, approvals)
    for error in stronger_metadata_errors(tile, entry):
        errors.append(f"{label}: manual safe pattern conflicts with stronger approved metadata: {error}.")
    return errors, warnings, bool(entry and entry.get("approved"))


def validate_pattern(
    pattern: dict[str, Any],
    *,
    class_names: set[str],
    collision_values: set[str],
    stylepack_ids: set[str],
    candidates: dict[str, dict[str, Any]],
    approvals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not pattern.get("patternId"):
        errors.append("patternId is required.")
    if not pattern.get("patternName"):
        errors.append("patternName is required.")
    if pattern.get("patternType") not in VALID_PATTERN_TYPES:
        errors.append(f"invalid patternType `{pattern.get('patternType')}`.")
    if pattern.get("category") not in VALID_CATEGORIES:
        errors.append(f"invalid category `{pattern.get('category')}`.")
    if not pattern.get("purpose"):
        errors.append("purpose is required.")
    if pattern.get("profile") not in VALID_PROFILES:
        errors.append(f"invalid profile `{pattern.get('profile')}`.")
    if pattern.get("approvedBy") != "human_safe_pattern_review":
        errors.append("approvedBy must be human_safe_pattern_review.")
    for target in pattern.get("stylepackTargets") or []:
        if target and target not in stylepack_ids:
            errors.append(f"stylepack target `{target}` does not exist.")
    tiles = pattern.get("tiles") or []
    if not tiles:
        errors.append("at least one tile is required.")
    approved_count = 0
    grid_cells: dict[tuple[int, int], str] = {}
    for index, tile in enumerate(tiles):
        tile_errors, tile_warnings, is_approved = validate_tile(
            tile,
            index,
            pattern,
            class_names=class_names,
            collision_values=collision_values,
            candidates=candidates,
            approvals=approvals,
        )
        errors.extend(tile_errors)
        warnings.extend(tile_warnings)
        approved_count += 1 if is_approved else 0
        if pattern.get("patternType") == "grid":
            grid_x = tile.get("gridX")
            grid_y = tile.get("gridY")
            if grid_x is None or grid_y is None:
                errors.append(f"tile #{index + 1}: grid patterns require gridX/gridY.")
            elif (int(grid_x), int(grid_y)) in grid_cells:
                errors.append(f"tile #{index + 1}: grid coordinate overlaps with `{grid_cells[(int(grid_x), int(grid_y))]}`.")
            else:
                grid_cells[(int(grid_x), int(grid_y))] = str(tile.get("candidateId"))
    layer_stack = pattern.get("layerStack") or {}
    for layer, value in layer_stack.items():
        if layer not in VALID_LAYERS:
            errors.append(f"layerStack contains invalid layer `{layer}`.")
        if value and value not in {tile.get("candidateId") for tile in tiles}:
            errors.append(f"layerStack `{layer}` references unknown pattern tile `{value}`.")
    rules = pattern.get("rules") or {}
    can_use_in_production = bool(rules.get("canUseInProduction"))
    if can_use_in_production and approved_count != len(tiles):
        errors.append("pattern cannot be production-ready until every tile is approved.")
    if errors:
        status = "invalid"
        production_status = "blocked"
    elif can_use_in_production and approved_count == len(tiles):
        status = "valid"
        production_status = "production_ready"
    elif approved_count == len(tiles):
        status = "valid"
        production_status = "valid_for_review"
    else:
        status = "needs_review"
        production_status = "valid_marker_only" if rules.get("allowMarkerFallback", True) else "blocked"
        warnings.append("one or more tiles are not approved; safe pattern is not production-ready.")
    return {
        "patternId": pattern.get("patternId"),
        "patternName": pattern.get("patternName"),
        "patternType": pattern.get("patternType"),
        "status": status,
        "productionStatus": production_status,
        "tileCount": len(tiles),
        "approvedTileCount": approved_count,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def validate_all(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = approval_utils.candidate_lookup()
    approvals = approval_utils.db_approval_lookup(candidates)
    class_names = load_class_names()
    collision_values = load_collision_values()
    stylepack_ids = load_stylepack_ids()
    results = [
        validate_pattern(
            pattern,
            class_names=class_names,
            collision_values=collision_values,
            stylepack_ids=stylepack_ids,
            candidates=candidates,
            approvals=approvals,
        )
        for pattern in patterns
    ]
    return {
        "generatedAt": now_iso(),
        "patternCount": len(patterns),
        "validCount": sum(1 for item in results if item["status"] == "valid"),
        "needsReviewCount": sum(1 for item in results if item["status"] == "needs_review"),
        "invalidCount": sum(1 for item in results if item["status"] == "invalid"),
        "productionReadyCount": sum(1 for item in results if item["productionStatus"] == "production_ready"),
        "results": results,
    }


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Manual Safe Pattern Validation Report",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Patterns checked: {summary['patternCount']}",
        f"- Valid: {summary['validCount']}",
        f"- Needs review: {summary['needsReviewCount']}",
        f"- Invalid: {summary['invalidCount']}",
        f"- Production ready: {summary['productionReadyCount']}",
        "",
        "## Pattern Results",
        "",
    ]
    for item in summary["results"]:
        lines.extend(
            [
                f"### {item.get('patternName') or item.get('patternId') or 'unnamed'}",
                "",
                f"- Pattern ID: `{item.get('patternId')}`",
                f"- Type: `{item.get('patternType')}`",
                f"- Status: `{item.get('status')}`",
                f"- Production status: `{item.get('productionStatus')}`",
                f"- Tiles: {item.get('approvedTileCount')}/{item.get('tileCount')} approved",
                f"- Errors: {len(item.get('errors') or [])}",
                f"- Warnings: {len(item.get('warnings') or [])}",
            ]
        )
        if item.get("errors"):
            lines.append("- Error details:")
            lines.extend(f"  - {error}" for error in item["errors"][:20])
        if item.get("warnings"):
            lines.append("- Warning details:")
            lines.extend(f"  - {warning}" for warning in item["warnings"][:20])
        lines.append("")
    if not summary["results"]:
        lines.append("- No manual safe patterns have been saved yet.")
    return "\n".join(lines)


def main() -> int:
    patterns = pattern_list(load_json(PATTERN_PATH, {"patterns": []}))
    summary = validate_all(patterns)
    write_text(REPORT_PATH, markdown_report(summary))
    print(f"Manual safe pattern validation complete: {summary['invalidCount']} invalid, {summary['needsReviewCount']} needs review.")
    return 1 if summary["invalidCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
