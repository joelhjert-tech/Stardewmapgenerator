#!/usr/bin/env python3
"""Migrate Tiled Map Assistant style packs to schemaVersion 2 marker-safe form."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tma_path_helpers import resolve_vanilla_authoritative_index, write_asset_path_config


TOOL_ROOT = Path(__file__).resolve().parent
STYLEPACK_DIR = TOOL_ROOT / "stylepacks"
REPORT_DIR = TOOL_ROOT / "reports"
BACKUP_DIR = TOOL_ROOT / "backups"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
GENERATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

VALID_LAYERS = ["Back", "Buildings", "Front", "AlwaysFront", "Paths"]
COLLISION_VALUES = [
    "unknown",
    "walkable",
    "blocked",
    "water_blocked",
    "decorative_front",
    "overlay_only",
    "marker_only",
    "custom_requires_review",
]

MARKER_ROLES = {
    "marker_ground": {"gid": 3001, "layer": "Back", "collision": "marker_only", "char": "."},
    "marker_wall": {"gid": 3002, "layer": "Buildings", "collision": "marker_only", "char": "#"},
    "marker_wall_top": {"gid": 3003, "layer": "AlwaysFront", "collision": "marker_only", "char": "T"},
    "marker_wall_body": {"gid": 3004, "layer": "Buildings", "collision": "marker_only", "char": "B"},
    "marker_corner": {"gid": 3005, "layer": "AlwaysFront", "collision": "marker_only", "char": "C"},
    "marker_edge": {"gid": 3006, "layer": "AlwaysFront", "collision": "marker_only", "char": "e"},
    "marker_transition": {"gid": 3007, "layer": "Back", "collision": "marker_only", "char": "~"},
    "marker_path": {"gid": 3008, "layer": "Paths", "collision": "marker_only", "char": "+"},
    "marker_entrance": {"gid": 3009, "layer": "Paths", "collision": "marker_only", "char": "E"},
    "marker_exit": {"gid": 3010, "layer": "Paths", "collision": "marker_only", "char": "X"},
    "marker_decoration_zone": {"gid": 3011, "layer": "Front", "collision": "marker_only", "char": "d"},
    "marker_blocked": {"gid": 3012, "layer": "Buildings", "collision": "marker_only", "char": "!"},
    "marker_protected": {"gid": 3013, "layer": "Paths", "collision": "marker_only", "char": "p"},
    "marker_water": {"gid": 3014, "layer": "Back", "collision": "marker_only", "char": "w"},
    "marker_overlay": {"gid": 3015, "layer": "AlwaysFront", "collision": "marker_only", "char": "o"},
}

GROUP_MARKERS = {
    "groundBaseTiles": "marker_ground",
    "groundVariationTiles": "marker_ground",
    "darkGroundTiles": "marker_edge",
    "lightGroundTiles": "marker_ground",
    "pathTiles": "marker_path",
    "transitionTiles": "marker_transition",
    "pathTransitionTiles": "marker_transition",
    "waterTiles": "marker_water",
    "waterEdgeTiles": "marker_water",
    "wallBodyTiles": "marker_wall_body",
    "wallTopTiles": "marker_wall_top",
    "wallSideTiles": "marker_wall",
    "cornerMatrices": "marker_corner",
    "edgeMatrices": "marker_edge",
    "rowMatrices": "marker_edge",
    "shadowTiles": "marker_edge",
    "canopyOverlayTiles": "marker_overlay",
    "decorationTiles": "marker_decoration_zone",
    "fillerTiles": "marker_wall",
    "rareDecorationTiles": "marker_decoration_zone",
    "torchTiles": "marker_overlay",
    "lightTiles": "marker_overlay",
    "ruinTiles": "marker_wall",
    "natureDetailTiles": "marker_decoration_zone",
    "sandBaseTiles": "marker_path",
    "sandDetailTiles": "marker_path",
    "forbiddenTiles": None,
}

TRANSITIONS = [
    "grass_to_sand",
    "grass_to_path",
    "grass_to_water",
    "floor_to_wall",
    "ruin_to_ground",
    "hedge_to_path",
    "cliff_to_ground",
]


def marker_ref(role: str, notes: str = "") -> dict:
    marker = MARKER_ROLES[role]
    return {
        "markerRole": role,
        "gid": marker["gid"],
        "source": "temporary_prototype_marker",
        "weight": 1,
        "active": True,
        "allowedLayers": [marker["layer"]],
        "collision": marker["collision"],
        "notes": notes or f"{role} marker fallback; not production art.",
    }


def transition_matrix() -> dict:
    ref = marker_ref("marker_transition", "Structural transition unresolved; marker-only output required.")
    return {
        "edges": {direction: ref for direction in ["N", "E", "S", "W"]},
        "innerCorners": {corner: ref for corner in ["NE", "NW", "SE", "SW"]},
        "outerCorners": {corner: ref for corner in ["NE", "NW", "SE", "SW"]},
        "fallback": ref,
    }


def border_matrix() -> dict:
    return {
        "body": {"default": marker_ref("marker_wall_body", "Wall/body structural tile unresolved; 946 quarantined.")},
        "front": {
            "topEdge": marker_ref("marker_wall_top"),
            "bottomEdge": marker_ref("marker_wall_top"),
            "leftEdge": marker_ref("marker_edge"),
            "rightEdge": marker_ref("marker_edge"),
            "frontCap": marker_ref("marker_wall_top"),
            "backCap": marker_ref("marker_wall_top"),
        },
        "alwaysFront": {
            "topEdge": marker_ref("marker_wall_top"),
            "bottomEdge": marker_ref("marker_wall_top"),
            "leftEdge": marker_ref("marker_edge"),
            "rightEdge": marker_ref("marker_edge"),
            "tallOverlay": marker_ref("marker_overlay"),
        },
        "darkGround": {
            "N": marker_ref("marker_edge"),
            "E": marker_ref("marker_edge"),
            "S": marker_ref("marker_edge"),
            "W": marker_ref("marker_edge"),
            "fallback": marker_ref("marker_edge"),
        },
        "corners": {corner: marker_ref("marker_corner") for corner in ["NE", "NW", "SE", "SW"]},
        "concaveCorners": {corner: marker_ref("marker_corner") for corner in ["NE", "NW", "SE", "SW"]},
        "convexCorners": {corner: marker_ref("marker_corner") for corner in ["NE", "NW", "SE", "SW"]},
        "edgeMatrices": {direction: marker_ref("marker_edge") for direction in ["N", "E", "S", "W"]},
        "rowMatrices": {direction: marker_ref("marker_edge") for direction in ["N", "E", "S", "W"]},
        "fillers": [marker_ref("marker_wall")],
    }


def default_groups() -> dict:
    groups = {}
    for group_name, marker_role in GROUP_MARKERS.items():
        groups[group_name] = [] if marker_role is None else [marker_ref(marker_role)]
    return groups


def density_rules(old: dict) -> dict:
    density = old.get("density", {})
    return {
        "groundVariationChance": density.get("groundVariation", 0.0),
        "darkBlendNearWalls": density.get("darkBlendNearWalls", 0.0),
        "decorationDensity": density.get("decoration", 0.0),
        "wallFillerDensity": density.get("wallFiller", 0.0),
        "forageDensity": density.get("forage", 0.0),
        "monsterDensity": density.get("monsterDensity", 0.0),
        "lightDensity": density.get("lights", 0.0),
        "borderBumpChance": density.get("borderBumpChance", 0.0),
        "borderBumpMaxDepth": density.get("borderBumpMax", 0),
        "variationChance": density.get("groundVariation", 0.0),
    }


def spacing_rules() -> dict:
    return {
        "protectedTileRadius": 3,
        "minPathWidth": 3,
        "maxEmptyAreaSize": 144,
        "minDecorationSpacing": 2,
        "minMonsterSpawnDistanceFromExit": 6,
        "minBorderDistanceForLargeObjects": 3,
    }


def tile_946_uses(value, path: str = "") -> list[dict]:
    found = []
    if isinstance(value, dict):
        local = value.get("localTileId")
        gid = value.get("gid")
        if local == 946 or gid == 947:
            found.append({"path": path or "/", "localTileId": local, "gid": gid, "value": value})
        for key, child in value.items():
            found.extend(tile_946_uses(child, f"{path}/{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(tile_946_uses(child, f"{path}/{index}"))
    return found


def scrub_tile_946_from_legacy_groups(value):
    if isinstance(value, list):
        scrubbed = []
        for item in value:
            if isinstance(item, dict) and (item.get("localTileId") == 946 or item.get("gid") == 947):
                continue
            scrubbed.append(scrub_tile_946_from_legacy_groups(item))
        return scrubbed
    if isinstance(value, dict):
        return {key: scrub_tile_946_from_legacy_groups(child) for key, child in value.items()}
    return value


def migrate_pack(path: Path) -> tuple[dict, list[dict]]:
    old = json.loads(path.read_text(encoding="utf-8"))
    old_groups = old.get("legacyGroupsBeforeSchemaV2") or old.get("groups") or old.get("semanticGroups") or {}
    old_groups = scrub_tile_946_from_legacy_groups(old_groups)
    uses_946 = tile_946_uses(old)
    groups = default_groups()
    marker_fallbacks = {role: marker_ref(role) for role in MARKER_ROLES}
    migrated = {
        "schemaVersion": 2,
        "stylePackId": old.get("stylePackId", path.stem),
        "description": old.get("description", "") + " Migrated to schema v2 marker-safe mode.",
        "draft": True,
        "inherits": old.get("inherits"),
        "approvedDatabasePreferred": True,
        "generationMode": "marker_only_until_structural_tiles_approved",
        "tilesheet": old.get("tilesheet") or {
            "name": "semantic_marker_tiles",
            "firstgid": 3001,
            "source": "marker_tests/semantic_marker_tiles.png",
            "tileWidth": 16,
            "tileHeight": 16,
            "imageWidth": 240,
            "imageHeight": 16,
            "tileCount": len(MARKER_ROLES),
            "columns": len(MARKER_ROLES),
        },
        "tilesheets": [old.get("tilesheet")] if old.get("tilesheet") else [],
        "tileIdPolicy": {
            "gidFormula": "marker-only semantic ids; production visual ids require approved candidate/profile references",
            "markerMode": True,
            "markerFirstgid": 3001,
            "markerTilesheet": "marker_tests/semantic_marker_tiles.png",
            "allowedSources": ["temporary_prototype_marker", "approved_moonvillage_database", "vanilla_stardew"],
            "restrictedSources": ["deepwoods_custom_lake_tilesheet", "deepwoods_infested_outdoors_tilesheet", "deepwoods_exclusive_assets"],
            "notes": "Schema v2 migration keeps final structural output marker-only until approved tile profiles exist.",
        },
        "variantPolicy": old.get("variantPolicy") or {
            "maxActiveVariantsPerDesignRole": 4,
            "overflowBehavior": "store_as_inactive_alternatives",
            "activeSelectionOrder": ["human_approval", "stable_layer_evidence", "source_style_consistency", "visual_design_usefulness"],
        },
        "markerTiles": {role: data["gid"] for role, data in MARKER_ROLES.items()},
        "markerFallbacks": marker_fallbacks,
        "terrainTransitions": {name: transition_matrix() for name in TRANSITIONS},
        "borderMatrices": {"hedge_or_forest": border_matrix()},
        "groups": groups,
        "legacyGroupsBeforeSchemaV2": old_groups,
        "legacyDensityBeforeSchemaV2": old.get("density", {}),
        "layerRules": {
            "ground": "Back",
            "blockingBody": "Buildings",
            "topEdge": "Front",
            "tallOverlay": "AlwaysFront",
            "path": "Paths",
            "transition": "Back",
            "darkBlend": "Back",
            "wallCollision": "Buildings",
            "wallTop": "AlwaysFront",
            "decoration": "Front",
            "lights": "Front",
            "water": "Back",
            "marker": "Front",
        },
        "collisionRules": {
            "ground": "marker_only",
            "path": "marker_only",
            "wall": "marker_only",
            "transition": "marker_only",
            "decoration": "marker_only",
            "water": "marker_only",
            "overlay": "marker_only",
        },
        "densityRules": density_rules(old),
        "spacingRules": spacing_rules(),
        "forbiddenTiles": [],
        "riskyTiles": [
            {
                "localTileId": 946,
                "gid": 947,
                "reason": "Quarantined: vanilla/Moonvillage evidence shows dominant AlwaysFront/canopy-style use with no intrinsic blocking property.",
                "forbiddenRoles": ["wall_body", "wallBodyTiles", "Buildings", "blockingBody", "wallCollision", "blocker", "collision", "hedge_body", "wall_base"],
                "allowedOnlyWithProfiles": ["canopy_alwaysfront", "front_overlay"],
            }
        ],
        "quarantinedTiles": [
            {
                "localTileId": 946,
                "gid": 947,
                "oldUsesRemoved": uses_946,
                "newStatus": "quarantined_not_available_for_generation",
            }
        ],
        "migrationNotes": [
            "Active groups are marker-only because approved structural tiles are not available.",
            "Legacy semantic groups are preserved for intent but are not generation output.",
            "Tile 946 is removed from unsafe wall/body/blocking roles and listed under risky/quarantined tiles.",
        ],
    }
    return migrated, uses_946


def harden_schema(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["required"] = sorted(set(schema.get("required", [])) | {"markerFallbacks"})
    props = schema.setdefault("properties", {})
    props["draft"] = {"type": "boolean"}
    props["generationMode"] = {"type": "string"}
    props["tilesheets"] = {"type": "array", "items": props.get("tilesheet", {"type": "object"})}
    props["markerFallbacks"] = {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}}
    props["legacyGroupsBeforeSchemaV2"] = {"type": "object"}
    props["legacyDensityBeforeSchemaV2"] = {"type": "object"}
    props["riskyTiles"] = schema["$defs"]["riskyTiles"]
    props["quarantinedTiles"] = {"type": "array", "items": {"type": "object"}}
    props["forbiddenTiles"] = {"type": "array", "items": {"$ref": "#/$defs/tileRef"}}
    defs = schema.setdefault("$defs", {})
    tile_ref = defs.setdefault("tileRef", {})
    variants = tile_ref.setdefault("oneOf", [])
    for variant in variants:
        if isinstance(variant, dict) and variant.get("type") == "object":
            vprops = variant.setdefault("properties", {})
            vprops["collision"] = {"enum": COLLISION_VALUES}
            vprops["markerRole"] = {"type": "string"}
            vprops["active"] = {"type": "boolean"}
    collision_rules = props.setdefault("collisionRules", {"type": "object"})
    collision_rules["additionalProperties"] = {"enum": COLLISION_VALUES}
    policy = schema.setdefault("x-moonvillageProjectPolicies", {})
    policy["collisionValues"] = COLLISION_VALUES
    policy["requiredMarkerRoles"] = list(MARKER_ROLES)
    policy["maxActiveVariantsPerDesignRole"] = 4
    policy["riskyTiles"] = [
        {
            "localTileId": 946,
            "gid": 947,
            "reason": "Quarantined from wall/body/blocking roles.",
            "forbiddenRoles": ["wall_body", "wallBodyTiles", "Buildings", "blockingBody", "wallCollision", "blocker", "collision", "hedge_body", "wall_base"],
            "allowedOnlyWithProfiles": ["canopy_alwaysfront", "front_overlay"],
        }
    ]
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def write_collision_schema(path: Path) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Moonvillage Collision Vocabulary",
        "type": "string",
        "enum": COLLISION_VALUES,
        "descriptions": {
            "unknown": "No approved collision behavior yet.",
            "walkable": "Can be walked on.",
            "blocked": "Blocks movement.",
            "water_blocked": "Water or water-like blocked/special terrain.",
            "decorative_front": "Decorative Front-layer tile that should not block movement.",
            "overlay_only": "AlwaysFront/overlay tile with no collision by itself.",
            "marker_only": "Debug/semantic marker, never production art.",
            "custom_requires_review": "Custom behavior requiring a separate validator rule.",
        },
    }
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"stylepacks.before_schema_v2.{TIMESTAMP}"
    backup_path.mkdir(parents=True, exist_ok=False)
    stylepack_files = [
        path for path in sorted(STYLEPACK_DIR.glob("*.json"))
        if path.name not in {"stylepack_schema.json", "collision_schema.json"}
    ]
    for path in stylepack_files:
        shutil.copy2(path, backup_path / path.name)

    harden_schema(STYLEPACK_DIR / "stylepack_schema.json")
    write_collision_schema(STYLEPACK_DIR / "collision_schema.json")

    changes = []
    for path in stylepack_files:
        migrated, uses_946 = migrate_pack(path)
        path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
        changes.append({"file": str(path), "tile946UsesBefore": uses_946, "status": "migrated_marker_only_schema_v2"})

    config_path = write_asset_path_config(TOOL_ROOT)
    vanilla_resolution = resolve_vanilla_authoritative_index(TOOL_ROOT)

    migration_lines = [
        "# Stylepack Migration Summary",
        "",
        f"- Generated: {GENERATED_AT}",
        f"- Backup path: `{backup_path}`",
        f"- Stylepacks migrated: {len(stylepack_files)}",
        "- New schema version: 2",
        "- Active generation mode: marker-only until approved structural tiles exist",
        "",
        "## Migrated Files",
        "",
    ]
    for change in changes:
        migration_lines.append(f"- `{Path(change['file']).name}`: {change['status']}; 946 uses before migration: {len(change['tile946UsesBefore'])}")
    migration_lines.extend([
        "",
        "## Preservation",
        "",
        "- Previous `groups` / `semanticGroups` data is preserved under `legacyGroupsBeforeSchemaV2`.",
        "- Previous density values are preserved and mapped into `densityRules`.",
        "- Active output groups now point to marker fallbacks, not unapproved final visual tile IDs.",
        "",
        "## Safety",
        "",
        "- Tile 946 was removed from active wall/body/blocking groups and moved to `riskyTiles` / `quarantinedTiles`.",
        "- Every required marker role is present in `markerFallbacks`.",
        "- `collision_schema.json` defines the normalized collision vocabulary.",
    ])
    (REPORT_DIR / "stylepack_migration_summary.md").write_text("\n".join(migration_lines) + "\n", encoding="utf-8")

    quarantine_lines = [
        "# Tile 946 Quarantine Enforcement",
        "",
        f"- Generated: {GENERATED_AT}",
        "- Policy: tile 946 / gid 947 is forbidden in Buildings, wall body, hedge body, blocker, collision, wall base, and blocking roles.",
        "",
        "## Results",
        "",
    ]
    for change in changes:
        name = Path(change["file"]).name
        if change["tile946UsesBefore"]:
            for use in change["tile946UsesBefore"]:
                quarantine_lines.append(f"- `{name}` `{use['path']}`: removed from active output and moved to `quarantinedTiles`; reason: no approved blocking profile and vanilla/Moonvillage evidence favors AlwaysFront/canopy-style use.")
        else:
            quarantine_lines.append(f"- `{name}`: no active tile 946 use found; quarantine policy added.")
    (REPORT_DIR / "tile_946_quarantine_enforcement.md").write_text("\n".join(quarantine_lines) + "\n", encoding="utf-8")

    vanilla_lines = [
        "# Vanilla Index Path Resolution",
        "",
        f"- Generated: {GENERATED_AT}",
        f"- Expected path: `{vanilla_resolution['expectedPath']}`",
        f"- Actual path: `{vanilla_resolution['actualPath']}`",
        f"- Config pointer: `{config_path}`",
        f"- Compatibility copy needed: `{vanilla_resolution['needsCompatibilityCopy']}`",
        "",
        "## Recommendation",
        "",
        vanilla_resolution["recommendation"],
        "",
        "Future scripts should call `tma_path_helpers.resolve_vanilla_authoritative_index()` or read `config/asset_paths.json` instead of hard-coding the missing database path.",
    ]
    (REPORT_DIR / "vanilla_index_path_resolution.md").write_text("\n".join(vanilla_lines) + "\n", encoding="utf-8")

    print(f"Migrated {len(stylepack_files)} stylepacks. Backup: {backup_path}")


if __name__ == "__main__":
    main()
