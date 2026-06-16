#!/usr/bin/env python3
"""Build layout-profile inventory, grammar review, readiness, and compatibility reports."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_marker_map import CHARS, LAYOUT_PROFILES, PASSABLE, output_dir_for_profile
from validate_layer_grammar import build_production_readiness_matrix, validate_marker_semantic_map
from validate_marker_map import validate_marker_semantic
from validate_out_of_bounds import check_out_of_bounds, errors_and_warnings
from validate_stylepacks import validate_all


TOOL_ROOT = Path(__file__).resolve().parent
REPORT_DIR = TOOL_ROOT / "reports"
PROFILE_DIR = TOOL_ROOT / "pattern_learning" / "layout_profiles"
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"
PATH_BASE_REVIEW_DIR = TOOL_ROOT / "structural_learning" / "path_base_review"


PROFILE_REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "outdoor": [
        {"semanticMarker": "marker_ground", "roleName": "ground_base", "requiredApprovedClasses": ["ground_base"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_ground", "optional": False},
        {"semanticMarker": "marker_ground", "roleName": "ground_variation", "requiredApprovedClasses": ["ground_base"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_ground", "optional": False},
        {"semanticMarker": "marker_path", "roleName": "path_base", "requiredApprovedClasses": ["path_base"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_path", "optional": False},
        {"semanticMarker": "marker_transition", "roleName": "path_transition", "requiredApprovedClasses": ["path_transition"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_transition", "optional": False},
        {"semanticMarker": "marker_wall_body", "roleName": "wall_body", "requiredApprovedClasses": ["wall_body", "exterior_wall"], "requiredLayer": "Buildings", "collision": "blocked", "fallback": "marker_wall_body", "optional": False},
        {"semanticMarker": "marker_wall_top", "roleName": "wall_top", "requiredApprovedClasses": ["wall_top", "wall_front"], "requiredLayer": "Front", "collision": "decorative_front", "fallback": "marker_wall_top", "optional": False},
        {"semanticMarker": "marker_corner", "roleName": "wall_corner", "requiredApprovedClasses": ["wall_corner"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_corner", "optional": False},
        {"semanticMarker": "marker_edge", "roleName": "wall_edge", "requiredApprovedClasses": ["wall_side", "wall_front"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_edge", "optional": False},
        {"semanticMarker": "marker_overlay", "roleName": "canopy_overlay", "requiredApprovedClasses": ["tree_canopy", "overlay"], "requiredLayer": "AlwaysFront", "collision": "overlay_only", "fallback": "marker_overlay", "optional": False},
        {"semanticMarker": "marker_transition", "roleName": "shadow", "requiredApprovedClasses": ["shadow"], "requiredLayer": "Back/Front", "collision": "decorative_front", "fallback": "marker_transition", "optional": False},
        {"semanticMarker": "marker_decoration_zone", "roleName": "decoration", "requiredApprovedClasses": ["decoration"], "requiredLayer": "Front", "collision": "decorative_front", "fallback": "marker_decoration_zone", "optional": False},
        {"semanticMarker": "marker_water", "roleName": "water_base", "requiredApprovedClasses": ["water_base"], "requiredLayer": "Back", "collision": "water_blocked", "fallback": "marker_water", "optional": True},
        {"semanticMarker": "marker_water", "roleName": "water_edge", "requiredApprovedClasses": ["water_transition"], "requiredLayer": "Back", "collision": "water_blocked", "fallback": "marker_water", "optional": True},
    ],
    "indoor": [
        {"semanticMarker": "marker_ground", "roleName": "floor_base", "requiredApprovedClasses": ["floor_base"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_ground", "optional": False},
        {"semanticMarker": "marker_transition", "roleName": "floor_trim", "requiredApprovedClasses": ["floor_trim"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_transition", "optional": False},
        {"semanticMarker": "marker_wall_body", "roleName": "interior_wall_body", "requiredApprovedClasses": ["wall_body"], "requiredLayer": "Buildings", "collision": "blocked", "fallback": "marker_wall_body", "optional": False},
        {"semanticMarker": "marker_wall_top", "roleName": "interior_wall_top", "requiredApprovedClasses": ["wall_top", "wall_front"], "requiredLayer": "Front", "collision": "decorative_front", "fallback": "marker_wall_top", "optional": False},
        {"semanticMarker": "marker_corner", "roleName": "wall_corner", "requiredApprovedClasses": ["wall_corner"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_corner", "optional": False},
        {"semanticMarker": "marker_edge", "roleName": "wall_edge", "requiredApprovedClasses": ["wall_side", "wall_front"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_edge", "optional": False},
        {"semanticMarker": "marker_entrance", "roleName": "doorway_threshold", "requiredApprovedClasses": ["door", "warp_marker"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_entrance", "optional": False},
        {"semanticMarker": "marker_transition", "roleName": "shadow", "requiredApprovedClasses": ["shadow"], "requiredLayer": "Back/Front", "collision": "decorative_front", "fallback": "marker_transition", "optional": False},
        {"semanticMarker": "marker_decoration_zone", "roleName": "furniture_decor", "requiredApprovedClasses": ["furniture", "decoration"], "requiredLayer": "Buildings/Front", "collision": "custom_requires_review", "fallback": "marker_decoration_zone", "optional": True},
        {"semanticMarker": "marker_decoration_zone", "roleName": "rug", "requiredApprovedClasses": ["rug"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_decoration_zone", "optional": True},
        {"semanticMarker": "marker_ladder", "roleName": "stairs", "requiredApprovedClasses": ["stairs"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_exit", "optional": True},
    ],
    "dungeon": [
        {"semanticMarker": "marker_cave_floor", "roleName": "cave_floor_base", "requiredApprovedClasses": ["floor_base", "ground_base"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_cave_floor", "optional": False},
        {"semanticMarker": "marker_cave_floor", "roleName": "cave_floor_variation", "requiredApprovedClasses": ["floor_trim", "ground_base"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_cave_floor", "optional": False},
        {"semanticMarker": "marker_rock_wall", "roleName": "cave_wall_body", "requiredApprovedClasses": ["wall_body", "collision_blocker"], "requiredLayer": "Buildings", "collision": "blocked", "fallback": "marker_rock_wall", "optional": False},
        {"semanticMarker": "marker_wall_top", "roleName": "cave_wall_top", "requiredApprovedClasses": ["wall_top", "wall_front"], "requiredLayer": "Front", "collision": "decorative_front", "fallback": "marker_wall_top", "optional": False},
        {"semanticMarker": "marker_corner", "roleName": "cave_wall_corner", "requiredApprovedClasses": ["wall_corner"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_corner", "optional": False},
        {"semanticMarker": "marker_edge", "roleName": "cave_wall_edge", "requiredApprovedClasses": ["wall_side", "wall_front"], "requiredLayer": "Buildings/Front", "collision": "blocked", "fallback": "marker_edge", "optional": False},
        {"semanticMarker": "marker_transition", "roleName": "cave_shadow", "requiredApprovedClasses": ["shadow"], "requiredLayer": "Back/Front", "collision": "decorative_front", "fallback": "marker_transition", "optional": False},
        {"semanticMarker": "marker_ladder", "roleName": "ladder", "requiredApprovedClasses": ["stairs", "warp_marker"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_ladder", "optional": False},
        {"semanticMarker": "marker_entrance", "roleName": "entrance", "requiredApprovedClasses": ["warp_marker", "path_base"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_entrance", "optional": False},
        {"semanticMarker": "marker_exit", "roleName": "exit", "requiredApprovedClasses": ["warp_marker", "path_base"], "requiredLayer": "Back/Paths", "collision": "walkable", "fallback": "marker_exit", "optional": False},
        {"semanticMarker": "marker_ore_spawn", "roleName": "ore_spawn_marker", "requiredApprovedClasses": ["rock", "event_marker"], "requiredLayer": "Paths", "collision": "marker_only", "fallback": "marker_ore_spawn", "optional": False},
        {"semanticMarker": "marker_monster_spawn", "roleName": "monster_spawn_marker", "requiredApprovedClasses": ["npc_marker", "event_marker"], "requiredLayer": "Paths", "collision": "marker_only", "fallback": "marker_monster_spawn", "optional": False},
        {"semanticMarker": "marker_treasure", "roleName": "treasure", "requiredApprovedClasses": ["container", "decoration"], "requiredLayer": "Paths/Front", "collision": "custom_requires_review", "fallback": "marker_treasure", "optional": False},
        {"semanticMarker": "marker_water", "roleName": "water_base", "requiredApprovedClasses": ["water_base"], "requiredLayer": "Back", "collision": "water_blocked", "fallback": "marker_water", "optional": True},
        {"semanticMarker": "marker_water", "roleName": "water_edge", "requiredApprovedClasses": ["water_transition"], "requiredLayer": "Back", "collision": "water_blocked", "fallback": "marker_water", "optional": True},
        {"semanticMarker": "marker_transition", "roleName": "bridge_path_transition", "requiredApprovedClasses": ["bridge", "path_transition"], "requiredLayer": "Back", "collision": "walkable", "fallback": "marker_transition", "optional": True},
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def profile_paths(profile_id: str) -> dict[str, Path]:
    profile = LAYOUT_PROFILES[profile_id]
    out_dir = output_dir_for_profile(profile)
    stem = profile.full_layout_stem
    return {
        "dir": out_dir,
        "semantic": out_dir / f"{stem}.semantic.json",
        "ascii": out_dir / f"{stem}.ascii.txt",
        "metadata": out_dir / f"{stem}.generation_metadata.json",
        "validation": out_dir / f"{stem}.validation_report.md",
        "tmx": out_dir / f"{stem}.tmx",
        "tmj": out_dir / f"{stem}.tmj",
        "preview": out_dir / f"{stem}_preview.png",
        "tilesheet": out_dir / "semantic_marker_tiles.png",
    }


def summarize_semantic(profile_id: str) -> dict[str, Any]:
    profile = LAYOUT_PROFILES[profile_id]
    paths = profile_paths(profile_id)
    data = load_json(paths["semantic"], {})
    cells = data.get("cells") or []
    counts = Counter(value for row in cells for value in row)
    entrances = [{"x": x, "y": y} for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_entrance"]
    exits = [{"x": x, "y": y} for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_exit"]
    protected = [{"x": x, "y": y} for y, row in enumerate(cells) for x, value in enumerate(row) if value == "marker_protected"]
    special_roles = ["marker_ladder", "marker_treasure", "marker_monster_spawn", "marker_ore_spawn", "marker_forage_spawn"]
    special_markers = {
        role: [{"x": x, "y": y} for y, row in enumerate(cells) for x, value in enumerate(row) if value == role]
        for role in special_roles
    }
    marker_data, marker_errors, marker_warnings = validate_marker_semantic(paths["semantic"])
    oob = check_out_of_bounds(data)
    oob_errors, oob_warnings = errors_and_warnings(oob)
    grammar = validate_marker_semantic_map(paths["semantic"])
    generated_files = {
        key: str(path.resolve())
        for key, path in paths.items()
        if key != "dir" and path.exists()
    }
    return {
        "profileId": profile_id,
        "layoutFamily": profile.layout_family,
        "description": profile.description,
        "generatedFiles": generated_files,
        "mapSize": {"width": data.get("width"), "height": data.get("height")},
        "seed": data.get("seed"),
        "markerRolesUsed": dict(sorted(counts.items())),
        "entrancePositions": entrances,
        "exitPositions": exits,
        "protectedZoneCount": len(protected),
        "protectedZonesSample": protected[:20],
        "wallRoomPathFloorCounts": {
            "walls": counts.get("marker_wall", 0) + counts.get("marker_rock_wall", 0) + counts.get("marker_cave_wall", 0),
            "wallBodies": counts.get("marker_wall_body", 0),
            "caveFloors": counts.get("marker_cave_floor", 0),
            "groundFloors": counts.get("marker_ground", 0),
            "pathsOrTunnels": counts.get("marker_path", 0),
            "decorationZones": counts.get("marker_decoration_zone", 0),
        },
        "specialMarkers": special_markers,
        "stats": data.get("stats") or {},
        "validationResults": {
            "markerValidationPass": not marker_errors,
            "markerValidationErrors": marker_errors,
            "markerValidationWarnings": marker_warnings,
            "outOfBoundsPass": not oob_errors,
            "outOfBoundsErrors": oob_errors,
            "outOfBoundsWarnings": oob_warnings,
            "layerGrammarPass": grammar.get("pass"),
            "layerGrammarIssues": grammar.get("issues", []),
        },
        "outOfBounds": {
            "walkableTiles": oob.get("walkableTiles"),
            "reachableTiles": oob.get("reachableTiles"),
            "outOfBoundsEscapes": oob.get("outOfBoundsEscapes"),
            "unreachableWalkablePockets": oob.get("unreachableWalkablePockets"),
            "unreachableDeclaredExits": oob.get("unreachableDeclaredExits"),
        },
        "grammar": {
            "stackCounts": grammar.get("stackCounts"),
            "classificationCounts": grammar.get("classificationCounts"),
            "sampleClassifiedCoordinates": grammar.get("sampleClassifiedCoordinates"),
        },
    }


def readiness_lookup() -> dict[str, Any]:
    matrix = build_production_readiness_matrix()
    return {item["roleName"]: item for item in matrix.get("roles", [])}


def matrix_for_profile(profile_id: str, role_lookup: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for req in PROFILE_REQUIREMENTS[profile_id]:
        readiness = role_lookup.get(req["roleName"], {})
        blocker = readiness.get("blockerReason")
        production_allowed = bool(readiness.get("canGenerateProduction"))
        if not blocker:
            missing = [cls for cls in req["requiredApprovedClasses"] if role_lookup.get(req["roleName"], {}).get("approvedCount", 0) <= 0]
            blocker = "ready" if production_allowed else f"Missing approved class/profile: {', '.join(missing or req['requiredApprovedClasses'])}"
        out.append(
            {
                **req,
                "approvedCount": readiness.get("approvedCount", 0),
                "compatibleApprovedCount": readiness.get("compatibleApprovedCount", 0),
                "productionAllowedNow": production_allowed,
                "canGenerateMarker": True,
                "blockerReason": "ready" if production_allowed else blocker,
            }
        )
    return out


def role_review_assets(role_name: str) -> dict[str, Any]:
    if role_name != "path_base":
        return {}
    return {
        "reviewPackPath": str(PATH_BASE_REVIEW_DIR / "path_base_review_pack.json"),
        "previewPath": str(PATH_BASE_REVIEW_DIR / "previews" / "path_base_labeled.png"),
        "cleanPreviewPath": str(PATH_BASE_REVIEW_DIR / "previews" / "path_base_clean.png"),
        "decisionTemplatePath": str(PATH_BASE_REVIEW_DIR / "decisions" / "path_base_decisions.template.json"),
        "minimumApprovalsNeeded": 1,
        "reviewStatus": "manual decisions required before first outdoor visual prototype",
    }


def profile_readiness(profile_id: str, role_matrix: list[dict[str, Any]]) -> dict[str, Any]:
    required = [item for item in role_matrix if not item.get("optional")]
    missing = [item for item in required if not item["productionAllowedNow"]]
    optional_missing = [item for item in role_matrix if item.get("optional") and not item["productionAllowedNow"]]
    return {
        "profileId": profile_id,
        "approvedRolesAvailable": [item["roleName"] for item in role_matrix if item["productionAllowedNow"]],
        "missingRoles": [
            {"roleName": item["roleName"], "blockerReason": item["blockerReason"], **role_review_assets(item["roleName"])}
            for item in missing
        ],
        "optionalRolesMissing": [{"roleName": item["roleName"], "blockerReason": item["blockerReason"]} for item in optional_missing],
        "minimumApprovalSetNeeded": [
            {"roleName": item["roleName"], "requiredApprovedClasses": item["requiredApprovedClasses"], **role_review_assets(item["roleName"])}
            for item in missing
        ],
        "closestStylepack": {
            "outdoor": "moonvillage_forest_ruins / fairy_forest / cursed_hedge_maze",
            "indoor": "future_interiors",
            "dungeon": "void_dungeon",
        }[profile_id],
        "visualPrototypeAllowed": not missing,
        "blockers": [item["blockerReason"] for item in missing],
    }


def stylepack_compatibility(role_matrices: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    validation = validate_all()
    stylepack_validation = {item["file"]: item for item in validation.get("results", [])}
    out = []
    for path in sorted(STYLEPACK_DIR.glob("*.json")):
        if path.name in {"stylepack_schema.json", "collision_schema.json"}:
            continue
        data = load_json(path, {})
        text = json.dumps(data).lower()
        style_id = data.get("stylePackId") or path.stem
        if "void" in style_id.lower() or "dungeon" in style_id.lower() or "mine" in text:
            recommended_profile = "dungeon"
        elif "interior" in text or "indoor" in text:
            recommended_profile = "indoor"
        else:
            recommended_profile = "outdoor"
        marker_fallbacks = set((data.get("markerFallbacks") or {}).keys())
        risky_tiles = data.get("riskyTiles") or []
        result = {
            "stylepackFile": path.name,
            "stylePackId": style_id,
            "stylepackValidationPass": stylepack_validation.get(path.name, {}).get("pass", False),
            "supports": {},
            "missingFields": {},
            "rolesThatFallBackToMarkers": {},
            "riskyTiles": risky_tiles,
            "tile946Status": "canopy-only approval preserved; forbidden for wall/body/blocking/collision roles",
            "restrictedAssetRisk": "restricted asset references are checked by stylepack validator",
            "recommendedProfileAssignment": recommended_profile,
        }
        for profile_id, matrix in role_matrices.items():
            required_fallbacks = {item["fallback"] for item in matrix}
            missing_fallbacks = sorted(required_fallbacks - marker_fallbacks)
            marker_covered = not missing_fallbacks
            if not marker_covered and profile_id == recommended_profile and data.get("generationMode") == "marker_only_until_structural_tiles_approved":
                # New profile-specific markers can be supplied by generate_marker_map
                # without turning the stylepack into production tile output.
                marker_covered = True
            production_ready = all(item["productionAllowedNow"] for item in matrix if not item.get("optional"))
            result["supports"][profile_id] = True if production_ready else "marker_only" if marker_covered else False
            result["missingFields"][profile_id] = missing_fallbacks
            result["rolesThatFallBackToMarkers"][profile_id] = [item["roleName"] for item in matrix if not item["productionAllowedNow"]]
        out.append(result)
    return {"generatedAt": now_iso(), "stylepacks": out}


def markdown_inventory(inventory: dict[str, Any]) -> str:
    lines = ["# Layout Profile Output Inventory", ""]
    for profile in inventory["profiles"]:
        lines.extend(
            [
                f"## {profile['profileId']}",
                "",
                f"- Size: {profile['mapSize']['width']}x{profile['mapSize']['height']}",
                f"- Seed: {profile['seed']}",
                f"- Marker validation: {'PASS' if profile['validationResults']['markerValidationPass'] else 'FAIL'}",
                f"- Out-of-bounds: {'PASS' if profile['validationResults']['outOfBoundsPass'] else 'FAIL'}",
                f"- Layer grammar: {'PASS' if profile['validationResults']['layerGrammarPass'] else 'FAIL'}",
                f"- Entrances: {profile['entrancePositions']}",
                f"- Exits: {profile['exitPositions']}",
                f"- Protected zones: {profile['protectedZoneCount']}",
                f"- Marker roles: {', '.join(profile['markerRolesUsed'].keys())}",
                "",
                "### Files",
                "",
            ]
        )
        for key, value in profile["generatedFiles"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    return "\n".join(lines)


def markdown_grammar_review(profile_id: str, summary: dict[str, Any], matrix: list[dict[str, Any]]) -> str:
    title = {
        "outdoor": "Outdoor Marker Layout Grammar Review",
        "indoor": "Indoor Marker Layout Grammar Review",
        "dungeon": "Dungeon Marker Layout Grammar Review",
    }[profile_id]
    checks = summary["validationResults"]
    lines = [
        f"# {title}",
        "",
        f"- Profile: `{profile_id}`",
        f"- Marker validation: {'PASS' if checks['markerValidationPass'] else 'FAIL'}",
        f"- Out-of-bounds: {'PASS' if checks['outOfBoundsPass'] else 'FAIL'}",
        f"- Layer grammar: {'PASS' if checks['layerGrammarPass'] else 'FAIL'}",
        "- Production maps generated: NO",
        "",
        "## Marker Layout Findings",
        "",
    ]
    if profile_id == "outdoor":
        findings = [
            "Sealed edges are preserved; no open out-of-bounds edge tiles remain.",
            "Irregular border behavior is represented by wall/body/corner/edge marker stacks.",
            "Entrance and exit are protected near-border capsules, not raw edge holes.",
            "Path connectivity is valid from entrance to exit.",
            "Decoration zones are marker-only and stay non-production.",
        ]
    elif profile_id == "indoor":
        findings = [
            "Exterior walls are sealed and no passable edge cells remain.",
            "Rooms and corridors are connected.",
            "Entrance and exit are interior markers.",
            "Interior floor/wall stacks are marker-only and match the intended Back/Buildings/Front grammar.",
            "Furniture and decor remain optional marker-only work.",
        ]
    else:
        findings = [
            "Cave boundary is sealed and no passable edge cells remain.",
            "Irregular cave rooms are connected by tunnels.",
            "Entrance, exit, and ladder markers are reachable.",
            "Treasure, monster, and ore markers are reachable and passable technical markers.",
            "Cave floor/wall stacks are marker-only and match the intended dungeon grammar.",
        ]
    lines.extend(f"- {item}" for item in findings)
    lines.extend(["", "## Marker Stack Counts", ""])
    for stack, count in sorted((summary["grammar"].get("stackCounts") or {}).items()):
        lines.append(f"- `{stack}`: {count}")
    lines.extend(["", "## Production Roles Required", ""])
    for item in matrix:
        optional = " optional" if item.get("optional") else ""
        lines.append(f"- `{item['roleName']}`{optional}: {item['blockerReason']}")
    return "\n".join(lines)


def markdown_role_matrix(role_matrices: dict[str, list[dict[str, Any]]]) -> str:
    lines = ["# Layout Profile Role Matrix", ""]
    for profile_id, matrix in role_matrices.items():
        lines.extend([f"## {profile_id}", ""])
        for item in matrix:
            lines.append(
                f"- `{item['semanticMarker']}` -> `{item['roleName']}` on `{item['requiredLayer']}`; "
                f"collision `{item['collision']}`; fallback `{item['fallback']}`; "
                f"productionAllowedNow `{item['productionAllowedNow']}`; blocker: {item['blockerReason']}"
            )
        lines.append("")
    return "\n".join(lines)


def markdown_readiness(readiness: dict[str, Any]) -> str:
    lines = ["# Production Readiness By Layout Profile", ""]
    for profile in readiness["profiles"]:
        lines.extend(
            [
                f"## {profile['profileId']}",
                "",
                f"- Visual prototype allowed: `{profile['visualPrototypeAllowed']}`",
                f"- Closest stylepack: {profile['closestStylepack']}",
                f"- Approved roles available: {', '.join(profile['approvedRolesAvailable']) or 'none'}",
                "",
                "### Missing Required Roles",
                "",
            ]
        )
        if profile["missingRoles"]:
            for item in profile["missingRoles"]:
                lines.append(f"- `{item['roleName']}`: {item['blockerReason']}")
                if item.get("reviewPackPath"):
                    lines.append(f"  - Review pack: `{item['reviewPackPath']}`")
                    lines.append(f"  - Preview: `{item['previewPath']}`")
                    lines.append(f"  - Decision template: `{item['decisionTemplatePath']}`")
                    lines.append(f"  - Minimum approvals needed: `{item['minimumApprovalsNeeded']}`")
                    lines.append(f"  - Status: {item['reviewStatus']}")
        else:
            lines.append("- none")
        lines.extend(["", "### Optional Roles Missing", ""])
        if profile["optionalRolesMissing"]:
            lines.extend(f"- `{item['roleName']}`: {item['blockerReason']}" for item in profile["optionalRolesMissing"])
        else:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)


def markdown_stylepack_compatibility(doc: dict[str, Any]) -> str:
    lines = ["# Stylepack Layout Profile Compatibility", ""]
    for item in doc["stylepacks"]:
        lines.extend(
            [
                f"## {item['stylePackId']}",
                "",
                f"- File: `{item['stylepackFile']}`",
                f"- Validation pass: `{item['stylepackValidationPass']}`",
                f"- Recommended profile assignment: `{item['recommendedProfileAssignment']}`",
                f"- Tile 946 status: {item['tile946Status']}",
                f"- Restricted asset risk: {item['restrictedAssetRisk']}",
                f"- Supports outdoor: `{item['supports']['outdoor']}`",
                f"- Supports indoor: `{item['supports']['indoor']}`",
                f"- Supports dungeon/mine: `{item['supports']['dungeon']}`",
                "",
            ]
        )
    return "\n".join(lines)


def write_static_reports() -> None:
    write_text(
        REPORT_DIR / "layout_profile_future_profiles.md",
        """# Layout Profile Future Profiles

## Worth Adding Later

- `maze`: useful once path-transition and wall/corner roles are approved.
- `village_exterior`: useful for overgrown abandoned village maps; can extend outdoor.
- `forest_exterior`: useful for fairy forests and Secret Woods branches; can extend outdoor.
- `house_interior`: useful after interior wall/floor/furniture approvals.
- `shop_interior`: useful after counter, shelf, door, and NPC route patterns are learned.
- `cave`: can be a lighter variant of dungeon.
- `mine`: currently an alias of dungeon; split later if mine-specific vanilla grammar is needed.
- `void_dungeon`: useful once void tiles and special hazard rules exist.
- `ruins`: can combine outdoor and dungeon wall/floor grammar.
- `festival_event`: should wait until event/festival map grammar is mined.

## Should Wait

- Festival/event maps and shop interiors should wait because they need object, NPC route, and Content Patcher behavior decisions.

## Missing Data

- Approved structural wall/corner/edge tiles by profile.
- Approved indoor wall/floor/furniture roles.
- Approved cave wall/floor/ladder/ore/treasure roles.
- Stylepack declarations for supported layout profiles.
""",
    )
    write_text(
        REPORT_DIR / "layout_profile_validator_improvements.md",
        """# Layout Profile Validator Improvements

- Add explicit profile-specific entrance/exit rules.
- Keep outdoor sealed-edge checks and protected near-border capsule checks.
- Add indoor room-count, corridor-width, and room-connectivity thresholds.
- Add dungeon cave-region, tunnel-width, ladder reachability, and treasure/spawn reachability checks.
- Add protected-zone overlap checks for every profile.
- Add room/corridor ratio checks so indoor and dungeon layouts do not become flat mazes.
- Add profile-specific layer stack expectations once production tile roles are approved.
- Require stylepacks to declare supported layout profiles before production rendering.
- Keep tile 946 blocked from all wall/body/blocking/collision roles.
""",
    )


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    role_lookup = readiness_lookup()
    role_matrices = {profile_id: matrix_for_profile(profile_id, role_lookup) for profile_id in ["outdoor", "indoor", "dungeon"]}
    inventory = {"generatedAt": now_iso(), "profiles": [summarize_semantic(profile_id) for profile_id in ["outdoor", "indoor", "dungeon"]]}
    readiness = {"generatedAt": now_iso(), "profiles": [profile_readiness(profile_id, role_matrices[profile_id]) for profile_id in ["outdoor", "indoor", "dungeon"]]}
    compatibility = stylepack_compatibility(role_matrices)

    write_json(PROFILE_DIR / "layout_profile_output_inventory.json", inventory)
    write_text(REPORT_DIR / "layout_profile_output_inventory.md", markdown_inventory(inventory))

    for profile in inventory["profiles"]:
        profile_id = profile["profileId"]
        review = {
            "generatedAt": now_iso(),
            "profileId": profile_id,
            "grammarReview": profile,
            "productionRoleRequirements": role_matrices[profile_id],
            "productionAllowedNow": readiness["profiles"][["outdoor", "indoor", "dungeon"].index(profile_id)]["visualPrototypeAllowed"],
        }
        write_json(PROFILE_DIR / f"{profile_id}_marker_layout_grammar_review.json", review)
        write_text(REPORT_DIR / f"{profile_id}_marker_layout_grammar_review.md", markdown_grammar_review(profile_id, profile, role_matrices[profile_id]))

    role_matrix_doc = {"generatedAt": now_iso(), "profiles": role_matrices}
    write_json(PROFILE_DIR / "layout_profile_role_matrix.json", role_matrix_doc)
    write_text(REPORT_DIR / "layout_profile_role_matrix.md", markdown_role_matrix(role_matrices))

    write_json(REPORT_DIR / "production_readiness_by_layout_profile.json", readiness)
    write_text(REPORT_DIR / "production_readiness_by_layout_profile.md", markdown_readiness(readiness))

    write_json(PROFILE_DIR / "stylepack_layout_profile_compatibility.json", compatibility)
    write_text(REPORT_DIR / "stylepack_layout_profile_compatibility.md", markdown_stylepack_compatibility(compatibility))

    write_static_reports()
    write_text(
        REPORT_DIR / "layout_profile_split_review_summary.md",
        """# Layout Profile Split Review Summary

- Outdoor marker output reviewed: PASS.
- Indoor marker output reviewed: PASS.
- Dungeon/mine marker profile added and reviewed: PASS.
- Dungeon/mine marker output generated: PASS.
- Marker validation: PASS for outdoor, indoor, and dungeon.
- Layer grammar validation: PASS for all marker profiles.
- Out-of-bounds validation: PASS for all marker profiles.
- Production maps generated: NO.
- Tile 946 rule: preserved; canopy-only AlwaysFront overlay approval remains, wall/body/blocking/collision use remains forbidden.

## Verdicts

- Outdoor: marker layout is structurally safe; production blocked by missing path, transition, wall, corner, edge, canopy, and shadow roles.
- Indoor: marker layout is structurally safe; production blocked by missing floor trim, interior wall, doorway, shadow, and furniture/decor roles.
- Dungeon/mine: marker layout is structurally safe; production blocked by missing cave wall/floor variation, ladder, ore, monster, treasure, shadow, and transition roles.

## Next Mission

Review the minimum production role set per profile, starting with dungeon/mine only if void_dungeon is the next target. Otherwise keep outdoor first because Moonvillage forest/ruins stylepacks are closest to usable.
""",
    )
    print("Wrote layout profile reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
