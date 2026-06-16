#!/usr/bin/env python3
"""Validate generated and copied maps against learned Stardew layer grammar.

This validator is intentionally conservative. It can pass marker-only semantic
maps while still blocking production tile output until structural tile profiles
are approved. Moonvillage maps are audited read-only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from learn_layer_patterns import infer_map_category, parse_tmx_stack, parse_tmj_stack
from validate_stylepacks import REQUIRED_MARKER_ROLES, STRUCTURAL_GROUPS, stylepack_files, validate_all as validate_stylepacks_all


TOOL_ROOT = Path(__file__).resolve().parent
PATTERN_ROOT = TOOL_ROOT / "pattern_learning"
COMBO_ROOT = PATTERN_ROOT / "layer_combinations"
NEW_VANILLA_CALIBRATION_ROOT = PATTERN_ROOT / "new_vanillaeditedmaps" / "calibration"
VANILLA_ROOT = PATTERN_ROOT / "vanilla"
REPORT_DIR = TOOL_ROOT / "reports"
MARKER_DIR = TOOL_ROOT / "generated_maps" / "marker_tests"
MAP_CATALOG = TOOL_ROOT / "database" / "map_catalog.json"
APPROVED_DB = TOOL_ROOT / "database" / "tile_database_v1_human_approved.json"
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"

STANDARD_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
VALID_RESULT_LEVELS = {
    "valid_vanilla_like",
    "valid_marker_only",
    "valid_custom_exception",
    "warning_needs_review",
    "warning_unusual_stack",
    "error_invalid_stack",
    "error_unsafe_collision",
    "error_unapproved_tile",
    "error_946_misuse",
    "error_missing_support_layer",
}
ERROR_LEVELS = {level for level in VALID_RESULT_LEVELS if level.startswith("error_")}
PASSABLE_MARKERS = {
    "marker_ground",
    "marker_cave_floor",
    "marker_path",
    "marker_entrance",
    "marker_exit",
    "marker_ladder",
    "marker_treasure",
    "marker_monster_spawn",
    "marker_ore_spawn",
    "marker_forage_spawn",
    "marker_decoration_zone",
    "marker_protected",
}
UNSAFE_COLLISION_VALUES = {"blocked", "blocks", "blocks_movement", "water_blocked"}
BLOCKING_CLASSES = {"collision_blocker", "wall_body", "wall_side", "wall_corner", "exterior_wall", "hedge_body"}
FRONT_SUPPORT_CLASSES = {"wall_top", "wall_front", "roof", "window", "door"}
OVERLAY_CLASSES = {"overlay", "tree_canopy", "roof", "exterior_decoration", "decoration"}

MARKER_ROLE_STACKS = {
    "marker_ground": ["Back"],
    "marker_cave_floor": ["Back"],
    "marker_wall": ["Back", "Buildings"],
    "marker_rock_wall": ["Back", "Buildings"],
    "marker_cave_wall": ["Back", "Buildings"],
    "marker_wall_top": ["Back", "Buildings", "Front"],
    "marker_wall_body": ["Back", "Buildings"],
    "marker_corner": ["Back", "Buildings", "Front"],
    "marker_edge": ["Back", "Buildings", "Front"],
    "marker_transition": ["Back"],
    "marker_path": ["Back", "Paths"],
    "marker_entrance": ["Back", "Paths"],
    "marker_exit": ["Back", "Paths"],
    "marker_ladder": ["Back", "Paths"],
    "marker_treasure": ["Back", "Paths"],
    "marker_monster_spawn": ["Back", "Paths"],
    "marker_ore_spawn": ["Back", "Paths"],
    "marker_forage_spawn": ["Back", "Paths"],
    "marker_decoration_zone": ["Back", "Front"],
    "marker_blocked": ["Back", "Buildings"],
    "marker_protected": ["Back"],
    "marker_water": ["Back"],
    "marker_overlay": ["Back", "AlwaysFront"],
}

ROLE_SPECS = [
    {"roleName": "ground_base", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["ground_base"], "markerRole": "marker_ground"},
    {"roleName": "ground_variation", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["ground_base"], "markerRole": "marker_ground"},
    {"roleName": "path_base", "requiredLayerStack": ["Back", "Paths"], "requiredApprovedTileClasses": ["path_base"], "markerRole": "marker_path"},
    {"roleName": "path_transition", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["path_transition"], "markerRole": "marker_transition"},
    {"roleName": "wall_body", "requiredLayerStack": ["Back", "Buildings"], "requiredApprovedTileClasses": ["wall_body", "exterior_wall"], "markerRole": "marker_wall_body"},
    {"roleName": "wall_top", "requiredLayerStack": ["Front"], "requiredApprovedTileClasses": ["wall_top", "wall_front"], "markerRole": "marker_wall_top"},
    {"roleName": "wall_corner", "requiredLayerStack": ["Buildings", "Front"], "requiredApprovedTileClasses": ["wall_corner"], "markerRole": "marker_corner"},
    {"roleName": "wall_edge", "requiredLayerStack": ["Buildings", "Front"], "requiredApprovedTileClasses": ["wall_side", "wall_front"], "markerRole": "marker_edge"},
    {"roleName": "canopy_overlay", "requiredLayerStack": ["AlwaysFront"], "requiredApprovedTileClasses": ["tree_canopy", "overlay"], "markerRole": "marker_overlay"},
    {"roleName": "front_overlay", "requiredLayerStack": ["Front"], "requiredApprovedTileClasses": ["overlay", "decoration"], "markerRole": "marker_decoration_zone"},
    {"roleName": "water_base", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["water_base"], "markerRole": "marker_water"},
    {"roleName": "water_edge", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["water_transition"], "markerRole": "marker_water"},
    {"roleName": "floor_base", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["floor_base"], "markerRole": "marker_ground"},
    {"roleName": "floor_trim", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["floor_trim"], "markerRole": "marker_transition"},
    {"roleName": "shadow", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["shadow"], "markerRole": "marker_transition"},
    {"roleName": "decoration", "requiredLayerStack": ["Front"], "requiredApprovedTileClasses": ["decoration"], "markerRole": "marker_decoration_zone"},
    {"roleName": "entrance", "requiredLayerStack": ["Back", "Paths"], "requiredApprovedTileClasses": ["warp_marker", "path_base"], "markerRole": "marker_entrance"},
    {"roleName": "exit", "requiredLayerStack": ["Back", "Paths"], "requiredApprovedTileClasses": ["warp_marker", "path_base"], "markerRole": "marker_exit"},
    {"roleName": "cave_floor_base", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["floor_base", "ground_base"], "markerRole": "marker_cave_floor"},
    {"roleName": "cave_floor_variation", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["floor_trim", "ground_base"], "markerRole": "marker_cave_floor"},
    {"roleName": "cave_wall_body", "requiredLayerStack": ["Back", "Buildings"], "requiredApprovedTileClasses": ["wall_body", "collision_blocker"], "markerRole": "marker_rock_wall"},
    {"roleName": "cave_wall_top", "requiredLayerStack": ["Front"], "requiredApprovedTileClasses": ["wall_top", "wall_front"], "markerRole": "marker_wall_top"},
    {"roleName": "cave_wall_corner", "requiredLayerStack": ["Buildings", "Front"], "requiredApprovedTileClasses": ["wall_corner"], "markerRole": "marker_corner"},
    {"roleName": "cave_wall_edge", "requiredLayerStack": ["Buildings", "Front"], "requiredApprovedTileClasses": ["wall_side", "wall_front"], "markerRole": "marker_edge"},
    {"roleName": "cave_shadow", "requiredLayerStack": ["Back"], "requiredApprovedTileClasses": ["shadow"], "markerRole": "marker_transition"},
    {"roleName": "ladder", "requiredLayerStack": ["Back", "Paths"], "requiredApprovedTileClasses": ["stairs", "warp_marker"], "markerRole": "marker_ladder"},
    {"roleName": "treasure", "requiredLayerStack": ["Back", "Paths"], "requiredApprovedTileClasses": ["container", "decoration"], "markerRole": "marker_treasure"},
    {"roleName": "monster_spawn_marker", "requiredLayerStack": ["Paths"], "requiredApprovedTileClasses": ["npc_marker", "event_marker"], "markerRole": "marker_monster_spawn"},
    {"roleName": "ore_spawn_marker", "requiredLayerStack": ["Paths"], "requiredApprovedTileClasses": ["rock", "event_marker"], "markerRole": "marker_ore_spawn"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def stack_id_from_layers(layers: set[str] | list[str]) -> str:
    ordered = [layer for layer in STANDARD_LAYERS if layer in set(layers)]
    return "+".join(ordered) if ordered else "empty"


def load_known_vanilla_stacks() -> set[str]:
    path = VANILLA_ROOT / "vanilla_layer_stack_patterns.json"
    if not path.exists():
        return {"empty", "Back", "Back+Buildings", "Back+Front", "Back+AlwaysFront", "Back+Paths", "Back+Buildings+Front"}
    data = load_json(path)
    return {entry.get("stackId") for entry in data.get("stackPatterns", []) if entry.get("stackId")}


def tile_classes(tile: dict[str, Any] | None) -> set[str]:
    if not tile:
        return set()
    classes = set(tile.get("approvedClasses") or [])
    if tile.get("finalClass"):
        classes.add(tile["finalClass"])
    return {str(c) for c in classes if c}


def tile_collision(tile: dict[str, Any] | None) -> str:
    if not tile:
        return "unknown"
    value = tile.get("collision") or tile.get("approvedCollision") or "unknown"
    if isinstance(value, list):
        return str(value[0]) if value else "unknown"
    return str(value)


def is_tile_approved(tile: dict[str, Any] | None) -> bool:
    if not tile:
        return False
    if tile.get("approved") is True:
        return True
    if tile.get("approvalBacked") is True:
        return True
    return bool(tile.get("approvedClasses") or tile.get("finalClass"))


def load_layer_grammar_exception_rules(path: Path | None = None) -> list[dict[str, Any]]:
    """Load optional audit-mode exception rules.

    These rules are intentionally ignored in production mode unless future
    generator code adds an explicit, separately validated production exception.
    """
    rules_path = path or (NEW_VANILLA_CALIBRATION_ROOT / "layer_grammar_exception_rules.json")
    if not rules_path.exists():
        return []
    data = load_json(rules_path)
    if isinstance(data, dict):
        rules = data.get("exceptionRules") or data.get("rules") or []
    elif isinstance(data, list):
        rules = data
    else:
        rules = []
    return [rule for rule in rules if isinstance(rule, dict)]


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def _tile_sheet_names(tile: dict[str, Any] | None) -> set[str]:
    if not tile:
        return set()
    names = {
        sheet_key(tile.get("sheet")),
        sheet_key(tile.get("tilesheetName")),
        sheet_key(tile.get("imageName")),
        sheet_key(tile.get("sourceTilesheet")),
    }
    return {name for name in names if name}


def _stack_tilesheet_names(tiles_by_layer: dict[str, dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for tile in tiles_by_layer.values():
        out |= _tile_sheet_names(tile)
    return out


def _stack_classes(tiles_by_layer: dict[str, dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for tile in tiles_by_layer.values():
        out |= tile_classes(tile)
    return out


def _edge_distance(x: int, y: int, tiles_by_layer: dict[str, dict[str, Any]]) -> int | None:
    dims = next(((tile.get("_mapWidth"), tile.get("_mapHeight")) for tile in tiles_by_layer.values() if tile.get("_mapWidth") and tile.get("_mapHeight")), None)
    if not dims:
        return None
    width, height = int(dims[0]), int(dims[1])
    if width <= 0 or height <= 0:
        return None
    return min(x, y, width - 1 - x, height - 1 - y)


def match_layer_grammar_exception(
    map_name: str,
    x: int,
    y: int,
    layer_stack: str,
    tiles_by_layer: dict[str, dict[str, Any]],
    exception_rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not exception_rules:
        return None
    map_category = next((tile.get("_mapCategory") for tile in tiles_by_layer.values() if tile.get("_mapCategory")), None) or infer_map_category(map_name)
    sheets = _stack_tilesheet_names(tiles_by_layer)
    classes = _stack_classes(tiles_by_layer)
    edge_distance = _edge_distance(x, y, tiles_by_layer)

    for rule in exception_rules:
        stacks = _as_set(rule.get("appliesToLayerStack"))
        if stacks and layer_stack not in stacks:
            continue
        categories = _as_set(rule.get("mapCategory"))
        if categories and "any" not in categories and map_category not in categories:
            continue
        allowed_sheets = _as_set(rule.get("allowedTilesheets"))
        if allowed_sheets and "any" not in allowed_sheets and not (sheets & allowed_sheets):
            continue
        allowed_classes = _as_set(rule.get("allowedClasses"))
        if allowed_classes and "any" not in allowed_classes and classes and not (classes & allowed_classes):
            continue
        forbidden_classes = _as_set(rule.get("forbiddenClasses"))
        if forbidden_classes and classes & forbidden_classes:
            continue
        context = rule.get("requiredTileContext") or {}
        if context.get("requiresMapBoundary"):
            max_distance = int(context.get("maxDistanceFromEdge", 0))
            if edge_distance is None or edge_distance > max_distance:
                continue
        if context.get("requiresPathsLayer") and "Paths" not in tiles_by_layer:
            continue
        if context.get("requiresVisualOverlay") and not ({"Front", "AlwaysFront"} & set(tiles_by_layer)):
            continue
        if context.get("mapNameRegex") and not re.search(str(context["mapNameRegex"]), map_name, re.IGNORECASE):
            continue
        return rule
    return None


def issue(
    map_name: str,
    x: int,
    y: int,
    layer_stack: str,
    result_level: str,
    severity: str,
    message: str,
    suggested_fix: str,
    rule_matched: str | None = None,
) -> dict[str, Any]:
    return {
        "mapName": map_name,
        "x": x,
        "y": y,
        "layerStack": layer_stack,
        "ruleMatched": rule_matched,
        "resultLevel": result_level,
        "severity": severity,
        "message": message,
        "suggestedFix": suggested_fix,
    }


def classify_layer_stack(
    map_name: str,
    x: int,
    y: int,
    tiles_by_layer: dict[str, dict[str, Any]],
    *,
    marker_only: bool = False,
    production_mode: bool = False,
    known_vanilla_stacks: set[str] | None = None,
    exception_rules: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Classify one coordinate stack and return (resultLevel, issues)."""
    known = known_vanilla_stacks or load_known_vanilla_stacks()
    present = {layer for layer in STANDARD_LAYERS if tiles_by_layer.get(layer)}
    layer_stack = stack_id_from_layers(present)
    issues: list[dict[str, Any]] = []
    matched_exception: dict[str, Any] | None = None
    matched_exception_level: str | None = None

    if marker_only:
        return "valid_marker_only", []

    for layer, tile in tiles_by_layer.items():
        classes = tile_classes(tile)
        collision = tile_collision(tile)
        local_id = tile.get("localTileId")
        if local_id == 946 and (layer == "Buildings" or collision in UNSAFE_COLLISION_VALUES or classes & BLOCKING_CLASSES):
            issues.append(issue(
                map_name, x, y, layer_stack, "error_946_misuse", "error",
                "Tile 946 is used in a wall/body/blocking/collision role.",
                "Remove tile 946 from blocking use; keep it marker/prototype-only until an overlay profile is approved.",
                "tile_946_quarantine",
            ))
        if layer == "AlwaysFront" and (collision in UNSAFE_COLLISION_VALUES or classes & BLOCKING_CLASSES):
            issues.append(issue(
                map_name, x, y, layer_stack, "error_unsafe_collision", "error",
                "AlwaysFront is carrying collision/blocking behavior.",
                "Move collision to Buildings or remove the blocking profile from the AlwaysFront tile.",
                "canopy_overlay",
            ))
        if production_mode and not is_tile_approved(tile):
            issues.append(issue(
                map_name, x, y, layer_stack, "error_unapproved_tile", "error",
                f"{layer} tile is not approved for production output.",
                "Use a marker fallback or approve a profile before production generation.",
                None,
            ))

    if "Buildings" in present and "Back" not in present:
        if not production_mode:
            matched_exception = match_layer_grammar_exception(map_name, x, y, layer_stack, tiles_by_layer, exception_rules or load_layer_grammar_exception_rules())
        if matched_exception and not production_mode:
            action = matched_exception.get("validatorAction", "needs_review")
            if action == "allow":
                matched_exception_level = "valid_custom_exception"
            elif action in {"warn", "needs_review"}:
                matched_exception_level = "warning_needs_review"
                issues.append(issue(
                    map_name, x, y, layer_stack, "warning_needs_review", "warning",
                    f"Buildings-without-Back matched audit exception `{matched_exception.get('exceptionId')}` but still needs review.",
                    "Keep this audit-only unless the generator implements this exact exception with approved tiles.",
                    matched_exception.get("exceptionId"),
                ))
            else:
                issues.append(issue(
                    map_name, x, y, layer_stack, "error_missing_support_layer", "error",
                    "Buildings tile has no Back/floor/ground support beneath it.",
                    "Add a valid Back-layer base beneath the Buildings tile or approve this as a custom exception.",
                    matched_exception.get("exceptionId"),
                ))
        else:
            issues.append(issue(
                map_name, x, y, layer_stack, "error_missing_support_layer", "error",
                "Buildings tile has no Back/floor/ground support beneath it.",
                "Add a valid Back-layer base beneath the Buildings tile or approve this as a custom exception.",
                "blocking_structure",
            ))

    front = tiles_by_layer.get("Front")
    if front and tile_classes(front) & FRONT_SUPPORT_CLASSES and "Buildings" not in present:
        issues.append(issue(
            map_name, x, y, layer_stack, "error_missing_support_layer", "error",
            "Front wall/top overlay appears without a supporting Buildings structure.",
            "Pair wall/top overlays with an approved Buildings body, or classify the tile as decoration instead.",
            "wall_with_overhead_top",
        ))

    if "Paths" in present and "Back" not in present:
        issues.append(issue(
            map_name, x, y, layer_stack, "warning_unusual_stack", "warning",
            "Paths layer appears without Back visual support.",
            "Treat Paths as technical route data and keep a valid Back base beneath it.",
            "technical_path",
        ))

    if "AlwaysFront" in present and not (present & {"Back", "Buildings"}):
        issues.append(issue(
            map_name, x, y, layer_stack, "warning_unusual_stack", "warning",
            "AlwaysFront appears without Back or Buildings support.",
            "Confirm this is a deliberate over-player overlay before using it in generator output.",
            "canopy_overlay",
        ))

    if "Front" in present and not (present & {"Back", "Buildings"}):
        issues.append(issue(
            map_name, x, y, layer_stack, "warning_unusual_stack", "warning",
            "Front appears without Back or Buildings support.",
            "Confirm this is decoration or add the expected support layer.",
            "wall_with_overhead_top",
        ))

    if any(i["severity"] == "error" for i in issues):
        first = next(i for i in issues if i["severity"] == "error")
        return first["resultLevel"], issues
    if issues:
        if any(i["resultLevel"] == "warning_needs_review" for i in issues):
            return "warning_needs_review", issues
        return "warning_unusual_stack", issues
    if matched_exception_level:
        return matched_exception_level, []
    if layer_stack in known:
        return "valid_vanilla_like", []
    return "warning_unusual_stack", [issue(
        map_name, x, y, layer_stack, "warning_unusual_stack", "warning",
        "Layer stack is not in the learned vanilla stack set.",
        "Review before allowing the generator to produce this stack.",
        None,
    )]


def neighbors4(x: int, y: int, width: int, height: int):
    for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny


def connected_marker_path(cells: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> bool:
    width = len(cells[0])
    height = len(cells)
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return True
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in seen or cells[ny][nx] not in PASSABLE_MARKERS:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return False


def validate_marker_semantic_map(path: Path, known_vanilla_stacks: set[str] | None = None) -> dict[str, Any]:
    data = load_json(path)
    map_name = data.get("mapName") or path.stem
    cells = data.get("cells") or []
    width = int(data.get("width") or (len(cells[0]) if cells else 0))
    height = int(data.get("height") or len(cells))
    issues: list[dict[str, Any]] = []
    classification_counts: Counter = Counter()
    stack_counts: Counter = Counter()
    examples: list[dict[str, Any]] = []

    if data.get("usesFinalVisualTileIds"):
        issues.append(issue(map_name, -1, -1, "marker_map", "error_unapproved_tile", "error", "Marker map claims final visual tile IDs.", "Keep marker map semantic-only.", None))
    if data.get("tile946BlockingRolesUsed"):
        issues.append(issue(map_name, -1, -1, "marker_map", "error_946_misuse", "error", "Marker metadata says tile 946 was used in a blocking role.", "Regenerate marker map without tile 946 blocking roles.", None))

    if not cells or any(len(row) != width for row in cells) or len(cells) != height:
        issues.append(issue(map_name, -1, -1, "invalid", "error_invalid_stack", "error", "Marker cell grid is missing or dimensions are inconsistent.", "Regenerate marker map.", None))
    else:
        entrances = [(x, y) for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_entrance"]
        exits = [(x, y) for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_exit"]
        if not entrances:
            issues.append(issue(map_name, -1, -1, "marker_map", "error_missing_support_layer", "error", "Entrance marker missing.", "Add marker_entrance.", "technical_path"))
        if not exits:
            issues.append(issue(map_name, -1, -1, "marker_map", "error_missing_support_layer", "error", "Exit marker missing.", "Add marker_exit.", "technical_path"))
        if entrances and exits and not connected_marker_path(cells, entrances[0], exits[0]):
            issues.append(issue(map_name, entrances[0][0], entrances[0][1], "Back+Paths", "error_invalid_stack", "error", "Entrance and exit are not connected through passable markers.", "Regenerate or repair semantic path.", "technical_path"))
        for y, row in enumerate(cells):
            for x, role in enumerate(row):
                stack_layers = MARKER_ROLE_STACKS.get(role)
                if not stack_layers:
                    issues.append(issue(map_name, x, y, "invalid", "error_invalid_stack", "error", f"Unknown marker role `{role}`.", "Use a defined marker fallback role.", None))
                    classification_counts["error_invalid_stack"] += 1
                    continue
                stack_id = stack_id_from_layers(set(stack_layers))
                classification_counts["valid_marker_only"] += 1
                stack_counts[stack_id] += 1
                if len(examples) < 20:
                    examples.append({"mapName": map_name, "x": x, "y": y, "markerRole": role, "layerStack": stack_id, "resultLevel": "valid_marker_only"})

    pass_state = not any(item["severity"] == "error" for item in issues)
    return {
        "mapName": map_name,
        "path": str(path),
        "mode": "marker_semantic",
        "pass": pass_state,
        "width": width,
        "height": height,
        "classificationCounts": dict(classification_counts),
        "stackCounts": dict(stack_counts),
        "issues": issues,
        "sampleClassifiedCoordinates": examples,
        "productionReadyClaimed": bool(data.get("usesFinalVisualTileIds")),
        "tile946BlockingRolesUsed": bool(data.get("tile946BlockingRolesUsed")),
    }


def validate_marker_maps() -> dict[str, Any]:
    known = load_known_vanilla_stacks()
    raw_marker_files = sorted(MARKER_DIR.glob("*.semantic.json")) + sorted(MARKER_DIR.glob("*/*.semantic.json"))
    marker_files = []
    for path in raw_marker_files:
        sibling_canonical = [item for item in path.parent.glob("*.semantic.json") if item.name != "marker_test_map.semantic.json"]
        if path.name == "marker_test_map.semantic.json" and sibling_canonical:
            continue
        marker_files.append(path)
    maps = [validate_marker_semantic_map(path, known) for path in marker_files]
    all_issues = [item for result in maps for item in result["issues"]]
    classification_counts = Counter()
    stack_counts = Counter()
    for result in maps:
        classification_counts.update(result["classificationCounts"])
        stack_counts.update(result["stackCounts"])
    return {
        "generatedAt": now_iso(),
        "mode": "marker_tests",
        "mapsScanned": len(marker_files),
        "pass": bool(marker_files) and not any(item["severity"] == "error" for item in all_issues),
        "classificationCounts": dict(classification_counts),
        "stackCounts": dict(stack_counts),
        "issues": all_issues,
        "maps": maps,
        "notes": [
            "Marker-only validation does not imply production tile approval.",
            "Marker roles are mapped to conceptual vanilla layer stacks for grammar testing.",
        ],
    }


def load_approved_profile_lookup() -> dict[str, dict[int, dict[str, Any]]]:
    """Compact sheet/localTileId lookup; only approved profiles are retained."""
    lookup: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    if not APPROVED_DB.exists():
        return lookup
    data = load_json(APPROVED_DB)
    for entry in data:
        if not entry.get("approved"):
            continue
        idx = entry.get("localTileId")
        if idx is None:
            continue
        try:
            idx = int(idx)
        except Exception:
            continue
        keys = {
            sheet_key(entry.get("imageName")),
            sheet_key(entry.get("tilesetName")),
            sheet_key(entry.get("copiedImagePath")),
        }
        profile = {
            "approved": True,
            "approvedClasses": [entry.get("finalClass")] if entry.get("finalClass") else [],
            "finalClass": entry.get("finalClass"),
            "finalPurpose": entry.get("finalPurpose"),
            "allowedLayers": entry.get("allowedLayers") or [],
            "collision": entry.get("collision") or "unknown",
            "localTileId": idx,
            "candidateId": entry.get("candidateId"),
            "approvalSource": entry.get("approvalSource"),
        }
        for key in keys:
            if key:
                lookup[key][idx] = profile
    return lookup


def sheet_key(value: Any) -> str:
    if value is None:
        return ""
    name = str(value).replace("\\", "/").split("/")[-1].lower()
    for suffix in [".png", ".tsx", ".json"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def approved_meta_for_tile(sheet: str, local_id: int | None, approved_lookup: dict[str, dict[int, dict[str, Any]]]) -> dict[str, Any]:
    if local_id is None:
        return {"approved": False, "approvedClasses": [], "collision": "unknown", "localTileId": local_id}
    meta = approved_lookup.get(sheet_key(sheet), {}).get(int(local_id))
    if meta:
        out = dict(meta)
        out["localTileId"] = int(local_id)
        return out
    return {"approved": False, "approvedClasses": [], "collision": "unknown", "localTileId": int(local_id)}


def validate_parsed_stack_map(
    parsed: dict[str, Any],
    *,
    map_name: str,
    production_mode: bool = False,
    approved_lookup: dict[str, dict[int, dict[str, Any]]] | None = None,
    known_vanilla_stacks: set[str] | None = None,
    exception_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    approved = approved_lookup or {}
    known = known_vanilla_stacks or load_known_vanilla_stacks()
    layers = parsed.get("layers", {})
    width = parsed.get("width", 0) or max((layer["width"] for layer in layers.values()), default=0)
    height = parsed.get("height", 0) or max((layer["height"] for layer in layers.values()), default=0)
    map_category = parsed.get("mapCategory") or infer_map_category(map_name)
    issues: list[dict[str, Any]] = []
    classification_counts: Counter = Counter()
    stack_counts: Counter = Counter()
    tile946_by_layer: Counter = Counter()
    examples: list[dict[str, Any]] = []

    for y in range(height):
        for x in range(width):
            tiles_by_layer: dict[str, dict[str, Any]] = {}
            for layer_name in STANDARD_LAYERS:
                raw = layers.get(layer_name, {}).get("tiles", {}).get((x, y))
                if not raw:
                    continue
                sheet, local_id = raw
                meta = approved_meta_for_tile(sheet, local_id, approved)
                meta["sheet"] = sheet
                meta["localTileId"] = local_id
                meta["_mapWidth"] = width
                meta["_mapHeight"] = height
                meta["_mapCategory"] = map_category
                tiles_by_layer[layer_name] = meta
                if local_id == 946:
                    tile946_by_layer[layer_name] += 1
            level, coord_issues = classify_layer_stack(
                map_name,
                x,
                y,
                tiles_by_layer,
                marker_only=False,
                production_mode=production_mode,
                known_vanilla_stacks=known,
                exception_rules=exception_rules,
            )
            stack_id = stack_id_from_layers(set(tiles_by_layer))
            classification_counts[level] += 1
            stack_counts[stack_id] += 1
            issues.extend(coord_issues)
            if len(examples) < 30 and (coord_issues or level == "warning_unusual_stack"):
                examples.append({"mapName": map_name, "x": x, "y": y, "layerStack": stack_id, "resultLevel": level})

    return {
        "mapName": map_name,
        "width": width,
        "height": height,
        "productionMode": production_mode,
        "classificationCounts": dict(classification_counts),
        "stackCounts": dict(stack_counts),
        "issues": issues[:5000],
        "issueCount": len(issues),
        "errorCount": sum(1 for item in issues if item["severity"] == "error"),
        "warningCount": sum(1 for item in issues if item["severity"] == "warning"),
        "tile946ByLayer": dict(tile946_by_layer),
        "sampleCoordinates": examples,
    }


def audit_moonvillage_maps() -> dict[str, Any]:
    if not MAP_CATALOG.exists():
        return {"generatedAt": now_iso(), "pass": False, "error": "map_catalog.json not found", "mapsAudited": 0}
    catalog = load_json(MAP_CATALOG)
    maps = [m for m in catalog if m.get("sourceCategory") == "moonvillage" and m.get("parseStatus") == "parsed"]
    approved_lookup = load_approved_profile_lookup()
    known = load_known_vanilla_stacks()
    audited = []
    parse_failures = []
    aggregate_counts: Counter = Counter()
    aggregate_issues: Counter = Counter()
    tile946_summary: Counter = Counter()
    maps_needing_review = []
    for item in maps:
        path = Path(item.get("copiedPath", ""))
        try:
            parsed = parse_tmx_stack(path) if path.suffix.lower() == ".tmx" else parse_tmj_stack(path)
            result = validate_parsed_stack_map(parsed, map_name=item.get("mapId") or path.stem, production_mode=False, approved_lookup=approved_lookup, known_vanilla_stacks=known)
        except Exception as exc:
            parse_failures.append({"mapId": item.get("mapId"), "copiedPath": item.get("copiedPath"), "error": str(exc)})
            continue
        result["sourceMod"] = item.get("sourceMod")
        result["copiedPath"] = item.get("copiedPath")
        aggregate_counts.update(result["classificationCounts"])
        for issue_item in result["issues"]:
            aggregate_issues[issue_item["resultLevel"]] += 1
        tile946_summary.update(result["tile946ByLayer"])
        if result["issueCount"] or result["tile946ByLayer"]:
            maps_needing_review.append({
                "mapName": result["mapName"],
                "sourceMod": result.get("sourceMod"),
                "issueCount": result["issueCount"],
                "errorCount": result["errorCount"],
                "warningCount": result["warningCount"],
                "tile946ByLayer": result["tile946ByLayer"],
                "copiedPath": result.get("copiedPath"),
            })
        audited.append(result)
    return {
        "generatedAt": now_iso(),
        "mode": "moonvillage_audit_read_only",
        "mapsAvailable": len(maps),
        "mapsAudited": len(audited),
        "parseFailures": parse_failures,
        "classificationCounts": dict(aggregate_counts),
        "issueLevelCounts": dict(aggregate_issues),
        "tile946UsageSummary": dict(tile946_summary),
        "mapsNeedingHumanInspection": sorted(maps_needing_review, key=lambda x: (x["errorCount"], x["warningCount"], sum(x["tile946ByLayer"].values())), reverse=True)[:100],
        "maps": audited,
        "notes": [
            "Audit mode does not modify Moonvillage maps.",
            "Warnings indicate review-needed grammar differences, not automatic map defects.",
            "Tile 946 remains quarantined from wall/body/blocking/collision generation.",
        ],
    }


def approved_class_counts() -> dict[str, Any]:
    counts: Counter = Counter()
    compatible_by_layer: dict[str, Counter] = defaultdict(Counter)
    if not APPROVED_DB.exists():
        return {"classCounts": {}, "classLayerCounts": {}}
    data = load_json(APPROVED_DB)
    for entry in data:
        if not entry.get("approved"):
            continue
        cls = entry.get("finalClass")
        if not cls:
            continue
        counts[cls] += 1
        for layer in entry.get("allowedLayers") or []:
            compatible_by_layer[cls][layer] += 1
    return {
        "classCounts": {k: int(v) for k, v in counts.items()},
        "classLayerCounts": {cls: {layer: int(count) for layer, count in layer_counts.items()} for cls, layer_counts in compatible_by_layer.items()},
    }


def role_readiness(spec: dict[str, Any], class_counts: dict[str, int], class_layer_counts: dict[str, dict[str, int]]) -> dict[str, Any]:
    required = spec["requiredApprovedTileClasses"]
    layers = spec["requiredLayerStack"]
    missing = []
    compatible_count = 0
    total_count = 0
    for cls in required:
        total = int(class_counts.get(cls, 0))
        total_count += total
        if not total:
            missing.append(cls)
            continue
        if layers:
            layer_ok = any(int(class_layer_counts.get(cls, {}).get(layer, 0)) > 0 for layer in layers)
            if layer_ok:
                compatible_count += sum(int(class_layer_counts.get(cls, {}).get(layer, 0)) for layer in layers)
            else:
                missing.append(f"{cls} on {('/'.join(layers))}")
    can_marker = spec.get("markerRole") in REQUIRED_MARKER_ROLES
    can_production = not missing
    return {
        "roleName": spec["roleName"],
        "requiredLayerStack": layers,
        "requiredApprovedTileClasses": required,
        "approvedCount": total_count,
        "compatibleApprovedCount": compatible_count,
        "canGenerateProduction": can_production,
        "canGenerateMarker": can_marker,
        "fallbackMarkerRole": spec.get("markerRole"),
        "blockerReason": "ready" if can_production else "Missing approved tile class/profile: " + ", ".join(missing),
        "suggestedNextAction": "Use production profile with validator checks." if can_production else f"Review and approve {', '.join(missing)}.",
    }


def build_production_readiness_matrix(counts: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = counts or approved_class_counts()
    class_counts = counts.get("classCounts", {})
    class_layer_counts = counts.get("classLayerCounts", {})
    roles = [role_readiness(spec, class_counts, class_layer_counts) for spec in ROLE_SPECS]
    structural_roles = {"wall_body", "wall_top", "wall_corner", "wall_edge", "canopy_overlay", "water_edge", "path_transition", "shadow"}
    blocked_structural = [role for role in roles if role["roleName"] in structural_roles and not role["canGenerateProduction"]]
    return {
        "generatedAt": now_iso(),
        "roles": roles,
        "allProductionReady": not blocked_structural and all(role["canGenerateProduction"] for role in roles),
        "structuralProductionReady": not blocked_structural,
        "blockedStructuralRoles": blocked_structural,
        "tile946Policy": "Tile 946 is not allowed to satisfy any wall/body/blocking/collision role.",
    }


def production_block_reasons(matrix: dict[str, Any]) -> list[str]:
    reasons = []
    if not matrix.get("structuralProductionReady"):
        missing = ", ".join(role["roleName"] for role in matrix.get("blockedStructuralRoles", []))
        reasons.append(f"Structural production tile roles are missing approved profiles: {missing}.")
    if not matrix.get("allProductionReady"):
        reasons.append("At least one semantic role still requires marker fallback.")
    return reasons


def compare_stylepacks_to_layer_grammar(matrix: dict[str, Any] | None = None) -> dict[str, Any]:
    matrix = matrix or build_production_readiness_matrix()
    role_by_name = {role["roleName"]: role for role in matrix["roles"]}
    generator_rules = load_json(COMBO_ROOT / "generator_layer_rules_from_vanilla.json")
    stylepack_summary = validate_stylepacks_all()
    results = []
    for path in stylepack_files():
        pack = load_json(path)
        marker_fallbacks = set((pack.get("markerFallbacks") or {}).keys())
        semantic_roles = []
        blocked_roles = []
        safe_stacks = []
        blocked_stacks = []
        for rule in generator_rules.get("rules", []):
            semantic = rule.get("semanticMarkerInput")
            fallback = rule.get("fallbackMarkerBehavior")
            role = role_by_name.get(semantic) or role_by_name.get(str(semantic).replace("ground_open", "ground_base"))
            available_marker = fallback in marker_fallbacks
            production_ready = bool(role and role.get("canGenerateProduction"))
            entry = {
                "semanticRole": semantic,
                "fallbackMarker": fallback,
                "markerAvailable": available_marker,
                "requiredLayers": rule.get("requiredLayers"),
                "productionReady": production_ready,
                "requiredApprovedTileClasses": rule.get("requiredApprovedTileClasses"),
            }
            semantic_roles.append(entry)
            if production_ready:
                safe_stacks.append(entry)
            else:
                blocked_roles.append(entry)
                blocked_stacks.append(entry)
        results.append({
            "stylepack": path.name,
            "stylePackId": pack.get("stylePackId", path.stem),
            "stylepackValidationPass": next((r["pass"] for r in stylepack_summary["results"] if r["file"] == path.name), False),
            "semanticRolesSupported": semantic_roles,
            "semanticRolesBlockedByMissingApprovedTileClasses": blocked_roles,
            "fallbackMarkerRolesAvailable": sorted(marker_fallbacks),
            "layerStacksThatCanBeProducedSafely": safe_stacks,
            "layerStacksBlocked": blocked_stacks,
            "structuralTileClassesStillMissing": sorted({cls for role in matrix["blockedStructuralRoles"] for cls in role["requiredApprovedTileClasses"]}),
        })
    return {
        "generatedAt": now_iso(),
        "stylepacksCompared": len(results),
        "stylepackValidationPass": stylepack_summary["pass"],
        "results": results,
    }


def write_marker_reports(summary: dict[str, Any]) -> None:
    write_json(REPORT_DIR / "marker_layer_grammar_validation.json", summary)
    lines = [
        "# Marker Layer Grammar Validation Report",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Result: {'PASS' if summary['pass'] else 'FAIL'}",
        f"- Marker maps scanned: {summary['mapsScanned']}",
        f"- Issues: {len(summary['issues'])}",
        "",
        "## Classification Counts",
        "",
    ]
    for key, count in sorted(summary["classificationCounts"].items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Stack Counts", ""])
    for key, count in sorted(summary["stackCounts"].items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- `{key}`: {count}")
    if summary["issues"]:
        lines.extend(["", "## Issues", ""])
        for item in summary["issues"][:80]:
            lines.append(f"- `{item['mapName']}` ({item['x']},{item['y']}) {item['resultLevel']}: {item['message']}")
    lines.extend([
        "",
        "## Safety Meaning",
        "",
        "- PASS means marker maps follow conceptual vanilla-like layer grammar.",
        "- PASS does not approve any production tile ID.",
        "- Production output remains blocked while structural classes are missing.",
    ])
    write_text(REPORT_DIR / "marker_layer_grammar_validation_report.md", "\n".join(lines))


def write_moon_reports(summary: dict[str, Any]) -> None:
    write_json(REPORT_DIR / "moonvillage_layer_grammar_audit.json", summary)
    lines = [
        "# Moonvillage Layer Grammar Audit",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Maps available: {summary.get('mapsAvailable', 0)}",
        f"- Maps audited: {summary.get('mapsAudited', 0)}",
        f"- Parse failures: {len(summary.get('parseFailures', []))}",
        "",
        "## Classification Counts",
        "",
    ]
    for key, count in sorted(summary.get("classificationCounts", {}).items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Issue Levels", ""])
    for key, count in sorted(summary.get("issueLevelCounts", {}).items()):
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## Tile 946 Usage Summary", ""])
    if summary.get("tile946UsageSummary"):
        for layer, count in sorted(summary["tile946UsageSummary"].items()):
            lines.append(f"- {layer}: {count}")
    else:
        lines.append("- No tile 946 usage found in audited Moonvillage maps.")
    lines.extend(["", "## Maps Needing Human Inspection", ""])
    for item in summary.get("mapsNeedingHumanInspection", [])[:40]:
        lines.append(f"- `{item['mapName']}`: errors={item['errorCount']}, warnings={item['warningCount']}, tile946={item['tile946ByLayer']}")
    lines.extend([
        "",
        "## Notes",
        "",
        "- This is read-only audit data. No Moonvillage map was changed.",
        "- Unusual stacks are review candidates, not automatic defects.",
        "- Tile 946 remains forbidden for generated wall/body/blocking/collision output.",
    ])
    write_text(REPORT_DIR / "moonvillage_layer_grammar_audit.md", "\n".join(lines))


def write_stylepack_report(summary: dict[str, Any]) -> None:
    lines = [
        "# Stylepack vs Layer Grammar Report",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Stylepacks compared: {summary['stylepacksCompared']}",
        f"- Stylepack validation pass: {summary['stylepackValidationPass']}",
        "",
    ]
    for result in summary["results"]:
        lines.extend([
            f"## {result['stylePackId']}",
            "",
            f"- File: `{result['stylepack']}`",
            f"- Semantic roles supported by marker fallback: {sum(1 for r in result['semanticRolesSupported'] if r['markerAvailable'])}",
            f"- Semantic roles blocked by missing approved tile classes: {len(result['semanticRolesBlockedByMissingApprovedTileClasses'])}",
            f"- Layer stacks production-safe now: {len(result['layerStacksThatCanBeProducedSafely'])}",
            f"- Layer stacks blocked: {len(result['layerStacksBlocked'])}",
            f"- Structural classes still missing: {', '.join(result['structuralTileClassesStillMissing']) or 'none'}",
            "",
        ])
    write_json(REPORT_DIR / "stylepack_vs_layer_grammar_report.json", summary)
    write_text(REPORT_DIR / "stylepack_vs_layer_grammar_report.md", "\n".join(lines))


def write_readiness_reports(matrix: dict[str, Any]) -> None:
    write_json(REPORT_DIR / "production_tile_readiness_matrix.json", matrix)
    lines = [
        "# Production Tile Readiness Matrix",
        "",
        f"- Generated: {matrix['generatedAt']}",
        f"- Structural production ready: {'YES' if matrix['structuralProductionReady'] else 'NO'}",
        f"- All production roles ready: {'YES' if matrix['allProductionReady'] else 'NO'}",
        "",
        "| Role | Stack | Approved Count | Production | Marker | Blocker |",
        "|---|---:|---:|---|---|---|",
    ]
    for role in matrix["roles"]:
        lines.append(
            f"| {role['roleName']} | `{'+'.join(role['requiredLayerStack'])}` | {role['approvedCount']} | "
            f"{'yes' if role['canGenerateProduction'] else 'no'} | {'yes' if role['canGenerateMarker'] else 'no'} | {role['blockerReason']} |"
        )
    write_text(REPORT_DIR / "production_tile_readiness_matrix.md", "\n".join(lines))


def write_implementation_summary(marker_summary: dict[str, Any], moon_summary: dict[str, Any], stylepack_summary: dict[str, Any], readiness: dict[str, Any]) -> None:
    lines = [
        "# Layer Grammar Implementation Summary",
        "",
        f"- Generated: {now_iso()}",
        "",
        "## Implemented",
        "",
        "- `validate_layer_grammar.py` with marker-map validation, Moonvillage read-only audit, stylepack grammar comparison, and production readiness matrix generation.",
        "- Coordinate-level result levels: `valid_vanilla_like`, `valid_marker_only`, `valid_custom_exception`, `warning_unusual_stack`, `error_invalid_stack`, `error_unsafe_collision`, `error_unapproved_tile`, `error_946_misuse`, `error_missing_support_layer`.",
        "- Generator safety gate integration through `generator_safety_gate.py`.",
        "",
        "## Results",
        "",
        f"- Marker grammar validation: {'PASS' if marker_summary['pass'] else 'FAIL'}",
        f"- Marker maps scanned: {marker_summary['mapsScanned']}",
        f"- Moonvillage maps audited: {moon_summary.get('mapsAudited', 0)}",
        f"- Moonvillage maps needing inspection: {len(moon_summary.get('mapsNeedingHumanInspection', []))}",
        f"- Stylepacks compared: {stylepack_summary['stylepacksCompared']}",
        f"- Structural production ready: {'YES' if readiness['structuralProductionReady'] else 'NO'}",
        f"- All production roles ready: {'YES' if readiness['allProductionReady'] else 'NO'}",
        "",
        "## Remaining Blockers",
        "",
    ]
    for role in readiness.get("blockedStructuralRoles", []):
        lines.append(f"- `{role['roleName']}`: {role['blockerReason']}")
    lines.extend([
        "",
        "## Next Recommended Mission",
        "",
        "Review and approve structural tile profiles for wall bodies, wall tops, corners, edges, transitions, canopy overlays, shadows, path transitions, and water edges; then rerun this validator before enabling production output.",
    ])
    write_text(REPORT_DIR / "layer_grammar_implementation_summary.md", "\n".join(lines))


def run_marker_validation_cli() -> dict[str, Any]:
    summary = validate_marker_maps()
    write_marker_reports(summary)
    return summary


def run_all() -> dict[str, Any]:
    marker_summary = run_marker_validation_cli()
    moon_summary = audit_moonvillage_maps()
    write_moon_reports(moon_summary)
    readiness = build_production_readiness_matrix()
    write_readiness_reports(readiness)
    stylepack_summary = compare_stylepacks_to_layer_grammar(readiness)
    write_stylepack_report(stylepack_summary)
    write_implementation_summary(marker_summary, moon_summary, stylepack_summary, readiness)
    return {
        "marker": marker_summary,
        "moonvillage": moon_summary,
        "readiness": readiness,
        "stylepacks": stylepack_summary,
        "pass": marker_summary["pass"] and stylepack_summary["stylepackValidationPass"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker-only", action="store_true", help="Only validate marker test maps.")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    args = parser.parse_args()
    if args.marker_only:
        summary = run_marker_validation_cli()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Marker layer grammar validation {'PASS' if summary['pass'] else 'FAIL'}; issues={len(summary['issues'])}")
        return 0 if summary["pass"] else 1
    summary = run_all()
    if args.json:
        print(json.dumps({"pass": summary["pass"], "markerPass": summary["marker"]["pass"], "structuralProductionReady": summary["readiness"]["structuralProductionReady"]}, indent=2))
    else:
        print(
            "Layer grammar validation "
            f"{'PASS' if summary['pass'] else 'FAIL'}; "
            f"markerPass={summary['marker']['pass']}; "
            f"structuralProductionReady={summary['readiness']['structuralProductionReady']}"
        )
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
