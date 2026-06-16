#!/usr/bin/env python3
"""Write the DeepWoods map-generation mastery review deliverables.

This script is intentionally report/prototype only. It does not modify
mission_assets, original Moonvillage maps, or generated production maps.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = ROOT / "tools" / "tiled-map-assistant"
REPORTS = TOOL_ROOT / "reports"
PROTOTYPES = TOOL_ROOT / "prototypes"
STYLEPACKS = TOOL_ROOT / "stylepacks"
GENERATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


PASS_MAP = [
    {
        "order": 1,
        "methodName": "DeepWoods.DeepWoods(parent, level, enterDir, spawnedFromObelisk)",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "198-243",
        "whatItDoes": "Creates a generated DeepWoods location, derives a deterministic seed/name, records parent/entry state, calls API OnCreate, creates map space, determines exits, builds the xTile map, and fills it with stuff and monsters.",
        "inputData": ["parent location", "level", "enter direction", "parent seed", "Game1 time/random for secondary RNG"],
        "outputMapChanges": ["new GameLocation state", "enter location", "exit list", "built runtime map", "placed objects/monsters after map generation"],
        "layersAffected": ["all layers indirectly"],
        "tileGroupsUsed": ["none directly"],
        "randomnessUsed": "Seeded by level, enter direction, parent seed; some later fill passes also mix in game time/random.",
        "safetyChecks": ["master-game checks in called methods", "network state gates before final map build"],
        "blockedTileChecks": "Deferred to FillLevel, StuffCreator, Monsters, and IsLocationOnBorderOrExit.",
        "moonvillageEquivalent": "MoonGeneratedLocation constructor or offline generator entrypoint that creates semantic state, picks seed, then calls generation phases in a stable order.",
        "shouldAdopt": "yes",
        "notes": "Keep this lifecycle, but make side effects explicit and testable for tools-side generation."
    },
    {
        "order": 2,
        "methodName": "CreateSpace",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "330-386",
        "whatItDoes": "Chooses first-level special map settings, otherwise determines clearing status, map dimensions, and enter location.",
        "inputData": ["level", "clearing settings", "map size settings", "API overrides", "enter direction"],
        "outputMapChanges": ["mapWidth", "mapHeight", "isLichtung", "enterLocation"],
        "layersAffected": [],
        "tileGroupsUsed": [],
        "randomnessUsed": "Chance-based clearing selection and size/entry choices.",
        "safetyChecks": ["master-game only", "minimum map dimensions derived from corner/exit requirements"],
        "blockedTileChecks": "Entry locations avoid corners through MinCornerDistanceForEnterLocation.",
        "moonvillageEquivalent": "Phase 1 semantic layout setup: choose biome, floor type, bounds, entrances, exits, protected zones.",
        "shouldAdopt": "yes",
        "notes": "Moonvillage should keep first floor/story floor special-case logic separate from generic floor generation."
    },
    {
        "order": 3,
        "methodName": "DetermineExits",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "288-328",
        "whatItDoes": "Selects exits, excludes the side the player entered from, uses special first-level behavior, and assigns target location names from deterministic seeds.",
        "inputData": ["enter direction", "level", "map size", "random exit positions"],
        "outputMapChanges": ["exits collection with exit directions, locations, target names"],
        "layersAffected": [],
        "tileGroupsUsed": [],
        "randomnessUsed": "1-3 exits on most levels; random edge positions with corner distance protection.",
        "safetyChecks": ["master-game only", "avoid opposite-of-entry loops unless parent return is explicit"],
        "blockedTileChecks": "Exit locations are later protected by ExitRadius.",
        "moonvillageEquivalent": "Dungeon ladder/door graph planner for generated floors, basements, maze exits, and Secret Woods return paths.",
        "shouldAdopt": "yes",
        "notes": "Do not let art placement decide exits. Exits are structural state first, then visualized."
    },
    {
        "order": 4,
        "methodName": "CreateEmptyMap",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "615-640",
        "whatItDoes": "Creates a runtime xTile Map, adds tilesheets, loads them through Game1.mapDisplayDevice, and adds Stardew-standard layers: Back, Buildings, Front, Paths, AlwaysFront.",
        "inputData": ["map name", "map width", "map height", "current season"],
        "outputMapChanges": ["new xTile Map with tilesheets and layers"],
        "layersAffected": ["Back", "Buildings", "Front", "Paths", "AlwaysFront"],
        "tileGroupsUsed": ["seasonal outdoors sheet", "DeepWoods infested sheet", "DeepWoods lake sheet"],
        "randomnessUsed": "None.",
        "safetyChecks": ["tilesheets are loaded before map use"],
        "blockedTileChecks": "None yet.",
        "moonvillageEquivalent": "Runtime map factory that always creates Stardew layer stack and loads approved style-pack tilesheets.",
        "shouldAdopt": "yes",
        "notes": "Use vanilla/Moonvillage-approved sheets; do not copy DeepWoods custom infested/lake sheets without license and asset approval."
    },
    {
        "order": 5,
        "methodName": "updateMap",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "651-693",
        "whatItDoes": "Creates a max-size empty placeholder map to avoid crashes, waits for seed/network/size readiness, then builds the real map and sorts layers.",
        "inputData": ["seed", "network state", "map dimensions", "override hooks"],
        "outputMapChanges": ["placeholder map if needed", "final runtime map", "sorted layers"],
        "layersAffected": ["all runtime layers"],
        "tileGroupsUsed": ["all groups used by builder"],
        "randomnessUsed": "Delegated to DeepWoodsBuilder.",
        "safetyChecks": ["do not rebuild when map id already matches", "set map id on override to avoid reload loop"],
        "blockedTileChecks": "Delegated.",
        "moonvillageEquivalent": "Safe runtime map lifecycle that never leaves Stardew with a null/half-built map and never reloads every frame.",
        "shouldAdopt": "yes",
        "notes": "This is important if Moonvillage moves from tools-side TMX prototypes into SMAPI runtime generation."
    },
    {
        "order": 6,
        "methodName": "DeepWoodsBuilder.Build",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "199-205, 265-289",
        "whatItDoes": "Orchestrates map drawing: forest border, clearing or forest patches, base ground fill, optional lake, and first-level minecart.",
        "inputData": ["DeepWoods state", "Map", "exit dictionary", "space manager", "random"],
        "outputMapChanges": ["border and patches", "ground fill", "clearing/lake shapes", "first-level special structure"],
        "layersAffected": ["Back", "Buildings", "Front", "AlwaysFront"],
        "tileGroupsUsed": ["grass groups", "forest row/corner matrices", "water/lake groups"],
        "randomnessUsed": "Weighted tile picks, row bumping, corner stepping, patch count/position, lake edge choices.",
        "safetyChecks": ["PlaceTile refuses out-of-bounds", "DONT_OVERRIDE by default preserves earlier matrix work"],
        "blockedTileChecks": "SpaceManager prevents patch overlap; exits are carved out of border rows.",
        "moonvillageEquivalent": "Single phase coordinator with explicit pass order: structural matrix work before broad fills, then validation.",
        "shouldAdopt": "yes",
        "notes": "Current Moonvillage generator should borrow the late non-overwrite base fill concept."
    },
    {
        "order": 7,
        "methodName": "GenerateForestBorder",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "357-390",
        "whatItDoes": "Generates four corners first, then fills the four side rows between the actual corner extents.",
        "inputData": ["map size", "corner matrices", "row matrices", "exit dictionary"],
        "outputMapChanges": ["irregular layered outer border"],
        "layersAffected": ["Back", "Buildings", "AlwaysFront"],
        "tileGroupsUsed": ["DeepWoodsCornerTileMatrix", "DeepWoodsRowTileMatrix"],
        "randomnessUsed": "Corner paths and row bumping downstream.",
        "safetyChecks": ["corner sizes determine row spans"],
        "blockedTileChecks": "Exit spans are skipped by row overload.",
        "moonvillageEquivalent": "Border generator that builds corner geometry before edges, not a plain rectangular fill.",
        "shouldAdopt": "yes",
        "notes": "This is a key reason DeepWoods avoids square-map stiffness."
    },
    {
        "order": 8,
        "methodName": "GenerateForestCorner",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "512-610",
        "whatItDoes": "Walks a corner shape with horizontal/vertical decisions, places concave/convex forest pieces, and writes dark/black grass shadows under the border.",
        "inputData": ["corner start", "x/y direction", "corner matrix"],
        "outputMapChanges": ["multi-tile corner shape", "dark grass edge/corner transitions", "corner light source"],
        "layersAffected": ["Back", "Buildings", "AlwaysFront"],
        "tileGroupsUsed": ["DeepWoodsCornerTileMatrix horizontal/front/vertical/corner fields", "dark grass", "black grass"],
        "randomnessUsed": "Chance weighted by corner aspect ratio chooses horizontal vs vertical steps.",
        "safetyChecks": ["PlaceTile bounds check", "PlaceMode.OVERRIDE only for intentional matrix corrections"],
        "blockedTileChecks": "Corner size contributes to safe exit distance.",
        "moonvillageEquivalent": "Corner matrix resolver for hedge, ruin wall, cliff, and maze borders.",
        "shouldAdopt": "yes",
        "notes": "Do not copy IDs directly; map roles to approved Moonvillage tile classes."
    },
    {
        "order": 9,
        "methodName": "GenerateForestRow",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "394-510",
        "whatItDoes": "Skips exit gaps, then walks a row with bump-in/bump-out variation, forest caps, concave/convex corners, filler behind protrusions, and shadow grass.",
        "inputData": ["placing direction", "row length", "exit direction", "row matrix", "exit radius"],
        "outputMapChanges": ["natural side border", "protected exit gap", "occluding canopy/front pieces", "dark edge strips"],
        "layersAffected": ["Back", "Buildings", "AlwaysFront"],
        "tileGroupsUsed": ["forest back/front arrays", "left/right corner fields", "dark/black grass fields", "forest filler"],
        "randomnessUsed": "Fifty-fifty bump decisions with max bump depth and row-end safety constraints.",
        "safetyChecks": ["row out-of-range guard", "max bump depth", "avoid bumping too close to row end"],
        "blockedTileChecks": "ExitRadius removes row segment around exits.",
        "moonvillageEquivalent": "Reusable border-row walker for fairy forest borders, hedge maze walls, and overgrown ruins.",
        "shouldAdopt": "yes",
        "notes": "This should replace flat repeated AlwaysFront border stamping."
    },
    {
        "order": 10,
        "methodName": "GenerateExits / GenerateExit",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "612-716",
        "whatItDoes": "Draws forest pieces to the sides of an exit, lays dark grass shadows around it, and grows a short bright-grass entry path with several randomized end caps.",
        "inputData": ["exit locations", "row matrix", "ExitRadius", "ExitLength", "clearing flag"],
        "outputMapChanges": ["visually framed exits", "bright transition paths", "exit lights"],
        "layersAffected": ["Back", "AlwaysFront"],
        "tileGroupsUsed": ["bright grass edges/corners", "dark grass sides", "forest left/right fronts"],
        "randomnessUsed": "Non-clearing exits choose a random bright-grass end shape.",
        "safetyChecks": ["exit gap already carved from border", "light source at each exit"],
        "blockedTileChecks": "ExitRadius is later protected from placement.",
        "moonvillageEquivalent": "Visual exit capsules for ladders, hidden basement doors, maze gates, and Secret Woods return exits.",
        "shouldAdopt": "yes",
        "notes": "Moonvillage should treat exits as protected visual structures, not just Warp properties."
    },
    {
        "order": 11,
        "methodName": "GenerateLichtung / GenerateLichtungCorner / FillLichtungRow",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "904-1093",
        "whatItDoes": "Creates a clearing by growing bright grass inward from side exits, choosing horizontal/vertical/steep corner pieces, filling rows, and adding light sources.",
        "inputData": ["side exit locations", "clearing tile matrix", "ExitLength", "light density"],
        "outputMapChanges": ["organic clearing boundary", "bright grass field", "center point", "lights"],
        "layersAffected": ["Back"],
        "tileGroupsUsed": ["DeepWoodsLichtungTileMatrix", "GrassTiles.BRIGHT"],
        "randomnessUsed": "Probability of horizontal movement changes with remaining x/y distance; optional light scatter.",
        "safetyChecks": ["argument guards for invalid side geometry", "entrance gap closure if side has no exit"],
        "blockedTileChecks": "Bright clearing tiles later reject random stuff placement.",
        "moonvillageEquivalent": "Fairy grove and overgrown village plaza generator with organic edges instead of box rooms.",
        "shouldAdopt": "yes",
        "notes": "This is a useful pattern for natural rooms and glades even outside forest maps."
    },
    {
        "order": 12,
        "methodName": "AddLakeToLichtung / GenerateLichtungLakeCorner",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "742-900",
        "whatItDoes": "Turns bright clearing area into water where appropriate, places animated lake edge/corner pieces, marks Water property, and adds lily decorations.",
        "inputData": ["clearing bounds", "lake matrix", "water tile groups", "water lily chances"],
        "outputMapChanges": ["lake body", "animated lake edge on Buildings", "Water property on Back", "lily shadows"],
        "layersAffected": ["Back", "Buildings"],
        "tileGroupsUsed": ["WATER_TILES", "WATER_LILY", "DeepWoodsLichtungTileMatrix WATER_*"],
        "randomnessUsed": "Water tile weights, lily chance, animation frame intervals.",
        "safetyChecks": ["uses bright-grass mask to decide lake region", "overrides last edge tile if needed"],
        "blockedTileChecks": "Water property later rejects placement and monster positions.",
        "moonvillageEquivalent": "Future fairy pond/void pool generator, but only after water edge tiles are approved.",
        "shouldAdopt": "partial",
        "notes": "Do not use DeepWoods custom lake sheet unless license and asset path are approved."
    },
    {
        "order": 13,
        "methodName": "GenerateGround",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "343-355",
        "whatItDoes": "Fills every empty Back tile with weighted normal grass using non-overwrite PlaceTile behavior.",
        "inputData": ["map dimensions", "GrassTiles.NORMAL"],
        "outputMapChanges": ["base ground for all untouched cells"],
        "layersAffected": ["Back"],
        "tileGroupsUsed": ["GrassTiles.NORMAL"],
        "randomnessUsed": "Weighted ground tile selection.",
        "safetyChecks": ["PlaceTile bounds check", "does not override earlier border/clearing/lake matrix work"],
        "blockedTileChecks": "None.",
        "moonvillageEquivalent": "Late base terrain fill after structural Back-layer transitions are already placed.",
        "shouldAdopt": "yes",
        "notes": "This pass order is the opposite of the naive fill-first approach and helps preserve detailed edges."
    },
    {
        "order": 14,
        "methodName": "GenerateForestPatches / TryGenerateForestPatch / GenerateForestPatch",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "1179-1292",
        "whatItDoes": "Adds interior forest islands using free rectangles, border rows on all four sides, interior filler, cleared corner corrections, and optional lights.",
        "inputData": ["map size", "patch density settings", "space manager", "row matrices"],
        "outputMapChanges": ["interior obstacle/forest patches", "dark corners", "light pockets"],
        "layersAffected": ["Back", "Buildings", "AlwaysFront"],
        "tileGroupsUsed": ["row matrices", "forest filler", "dark grass corners"],
        "randomnessUsed": "Two-dice patch count, random centers, random patch sizes, random row bumping.",
        "safetyChecks": ["minimum gap from border", "minimum patch size", "overlap shrink-or-fail"],
        "blockedTileChecks": "SpaceManager occupied rectangles prevent patch overlap.",
        "moonvillageEquivalent": "Interior hedge islands, ruin blocks, tree clumps, and maze chunks that preserve navigability.",
        "shouldAdopt": "yes",
        "notes": "Current Moonvillage internal walls need this kind of footprint manager."
    },
    {
        "order": 15,
        "methodName": "PlaceTile / PlaceAnimatedTile / ClearTile",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsBuilder.cs",
        "lineRange": "1102-1166",
        "whatItDoes": "Centralizes bounds checks and non-overwrite/override placement semantics.",
        "inputData": ["layer", "tile index or tile array", "coordinate or Placing offset", "PlaceMode"],
        "outputMapChanges": ["tile assignment", "animated tile assignment", "tile removal"],
        "layersAffected": ["any passed layer"],
        "tileGroupsUsed": ["any passed tile group"],
        "randomnessUsed": "Weighted/random array pick for tile arrays.",
        "safetyChecks": ["out-of-bounds returns false", "DONT_OVERRIDE preserves existing tile"],
        "blockedTileChecks": "Placement outcome can be used by filler passes.",
        "moonvillageEquivalent": "Single TilePlacer API with layer legality, approved tile profile, marker fallback, and no-overwrite policy.",
        "shouldAdopt": "yes",
        "notes": "Moonvillage should add approval/profile validation here."
    },
    {
        "order": 16,
        "methodName": "DeepWoodsSpaceManager.TryGetFreeRectangleForForestPatch",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsSpaceManager.cs",
        "lineRange": "66-107",
        "whatItDoes": "Tries to reserve a rectangle for a forest patch, shrinking it until it fits within world margins and avoids occupied rectangles.",
        "inputData": ["desired center", "desired width/height", "min size", "occupied rectangles", "border margins"],
        "outputMapChanges": ["none directly", "occupied rectangle reservation"],
        "layersAffected": [],
        "tileGroupsUsed": [],
        "randomnessUsed": "Caller provides random center and size.",
        "safetyChecks": ["rejects world-border intersections", "rejects occupied-rectangle intersections"],
        "blockedTileChecks": "Rectangular footprint reservations.",
        "moonvillageEquivalent": "Shared footprint reservation manager for rooms, ruin blocks, ponds, large decorations, and spawn pockets.",
        "shouldAdopt": "yes",
        "notes": "This should be generalized beyond forest patches."
    },
    {
        "order": 17,
        "methodName": "DeepWoodsStuffCreator.AddStuff / IsTileFree / CheckAndBlockSpace",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsStuffCreator.cs",
        "lineRange": "161-360, 890-934",
        "whatItDoes": "Shuffles all tiles, places large/special resources and small objects using chance tables, rejects blocked/Buildings/border/exit/water cells, and reserves multi-tile footprints.",
        "inputData": ["map size", "blockedLocations", "luck settings", "level", "season"],
        "outputMapChanges": ["terrainFeatures", "largeTerrainFeatures", "resourceClumps", "objects", "grass"],
        "layersAffected": ["game objects/features, not xTile layers"],
        "tileGroupsUsed": ["object/resource/terrain feature settings"],
        "randomnessUsed": "Shuffled candidate order and per-object chance checks.",
        "safetyChecks": ["large footprints checked before placement", "clearing bright grass protected", "winter density compensation"],
        "blockedTileChecks": ["blockedLocations", "Buildings layer occupied", "border/exit/enter protection", "Water property"],
        "moonvillageEquivalent": "MoonPlacementValidator used by decoration placer, forage spawner, dungeon generator, monster spawner, and NPC path checker.",
        "shouldAdopt": "yes",
        "notes": "Place large objects first, reserve footprints, then fill smaller details."
    },
    {
        "order": 18,
        "methodName": "DeepWoodsMonsters.AddMonsters / CanPlaceMonsterHere",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Generation/DeepWoodsMonsters.cs",
        "lineRange": "51-177",
        "whatItDoes": "Calculates monster count from map area/depth/density/infested state, shuffles candidate tiles, and rejects blocked, Buildings, border, exit, water, and footprint conflicts.",
        "inputData": ["map size", "level", "monster settings", "blockedLocations", "existing characters"],
        "outputMapChanges": ["characters collection"],
        "layersAffected": ["none directly"],
        "tileGroupsUsed": [],
        "randomnessUsed": "Two-dice count distribution, candidate shuffle, monster selection chance tables.",
        "safetyChecks": ["clearing non-infested maps skip monsters", "infested minimum count", "gliders bypass some footprint checks"],
        "blockedTileChecks": ["blockedLocations", "Buildings", "border/exit/enter", "Water", "NPC bounding boxes"],
        "moonvillageEquivalent": "Spawn planner for normal, cursed, maze, boss/event, and safe story floors.",
        "shouldAdopt": "yes",
        "notes": "The count model is useful, but monster species should be Moonvillage-specific."
    },
    {
        "order": 19,
        "methodName": "DeepWoods.CheckWarp / Warp / ValidateAndIfNecessaryCreateExitChildren",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/Map/DeepWoods.cs",
        "lineRange": "487-570, 721-817",
        "whatItDoes": "Creates child locations when exits need targets, detects border/additional-exit intersection, validates target location/position, fixes one-tile offset for some directions, and warps.",
        "inputData": ["player position", "exit graph", "parent/child names", "additional exit locations"],
        "outputMapChanges": ["child locations may be added to Game1.locations", "player warped"],
        "layersAffected": [],
        "tileGroupsUsed": [],
        "randomnessUsed": "None directly.",
        "safetyChecks": ["guard against null location request", "avoid zero target location", "client creates blank target before warp"],
        "blockedTileChecks": "Exit radius placement protection prevents decorative blocking.",
        "moonvillageEquivalent": "Anti-bug warp validation for ladders, hidden basement doors, maze exits, Secret Woods return warps, and generated floor transitions.",
        "shouldAdopt": "partial",
        "notes": "Adopt the validation pattern; tailor randomizing/lost behavior to Moonvillage story needs."
    },
    {
        "order": 20,
        "methodName": "DeepWoodsAPI hooks",
        "sourceFile": "tools/DeepWoodsMod-main/src/DeepWoods/API/Impl/DeepWoodsAPI.cs",
        "lineRange": "29-90, 102-190+",
        "whatItDoes": "Provides before/after/override hooks for map generation, fill, infestation, monsters, debris, plus registered custom features/objects/monsters.",
        "inputData": ["callbacks from other systems", "DeepWoods location"],
        "outputMapChanges": ["callbacks can modify or replace generation phases"],
        "layersAffected": ["depends on callback"],
        "tileGroupsUsed": ["depends on callback"],
        "randomnessUsed": "Callbacks decide.",
        "safetyChecks": ["callback exceptions are caught and logged as external-mod issues"],
        "blockedTileChecks": "Callback registrations include placement decision callbacks.",
        "moonvillageEquivalent": "Small generation hook bus for quest floors, seasonal variants, special events, custom monsters, treasure, style pack swaps, and AI-authored templates.",
        "shouldAdopt": "yes",
        "notes": "Keep hooks smaller and typed by generation phase so the core pipeline remains auditable."
    }
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pass_map_md() -> str:
    lines = [
        "# DeepWoods Generation Pass Map",
        "",
        f"- Generated: {GENERATED_AT}",
        "- Scope: technical review only; no assets copied and no Moonvillage maps modified.",
        "",
        "## Pass Order Summary",
        "",
    ]
    for item in PASS_MAP:
        lines.extend([
            f"### {item['order']}. {item['methodName']}",
            "",
            f"- Source: `{item['sourceFile']}:{item['lineRange']}`",
            f"- What it does: {item['whatItDoes']}",
            f"- Input data: {', '.join(item['inputData']) if item['inputData'] else 'none'}",
            f"- Output map changes: {', '.join(item['outputMapChanges']) if item['outputMapChanges'] else 'none'}",
            f"- Layers affected: {', '.join(item['layersAffected']) if item['layersAffected'] else 'none'}",
            f"- Tile groups used: {', '.join(item['tileGroupsUsed']) if item['tileGroupsUsed'] else 'none'}",
            f"- Randomness used: {item['randomnessUsed']}",
            f"- Safety checks: {', '.join(item['safetyChecks']) if item['safetyChecks'] else 'none'}",
            f"- Blocked tile checks: {item['blockedTileChecks']}",
            f"- Moonvillage equivalent: {item['moonvillageEquivalent']}",
            f"- Should adopt: **{item['shouldAdopt']}**",
            f"- Notes: {item['notes']}",
            "",
        ])
    return "\n".join(lines)


DEEPWOODS_AESTHETIC_RULES = """# DeepWoods Aesthetic Rules

- Generated: {generated_at}
- Scope: extract visual rules and Moonvillage equivalents. This is not an asset-copy plan.

## Rules To Adopt

### 1. Borders are generated as geometry, not decoration

DeepWoods rule:
Outer forest borders are made from generated corner shapes plus row walkers. Corners are generated first, then side rows fill the gap between the corner sizes.

Moonvillage equivalent:
Fairy forest, cursed hedge maze, ruins, and village-overgrowth maps should build a semantic border shape first. The renderer should then resolve corners, edges, caps, shadows, and overlays from that shape.

### 2. Straight rows are interrupted by bump-in/bump-out motion

DeepWoods rule:
`GenerateForestRow` tracks an inward offset and randomly bumps out or back within `MaxBumpSizeForForestBorder`. It also fills cells behind protrusions.

Moonvillage equivalent:
Any natural border should run through a border variation resolver. Plain rectangle borders should be reserved for intentional architecture, not forests or hedges.

### 3. The same border cell affects multiple layers

DeepWoods rule:
One forest cell can place dark ground on Back, blocking forest background on Buildings, and canopy/edge pieces on AlwaysFront.

Moonvillage equivalent:
Style packs must define border matrices by role and layer: Back shadow, Buildings collision/body, Front cap, and AlwaysFront canopy. AlwaysFront cannot be a random decoration pass.

### 4. Corners are matrix choices, not random edge tiles

DeepWoods rule:
Corner matrices distinguish horizontal back, vertical back, diagonal back, concave corner, convex corner, dark grass horizontal/vertical/corners, and black grass variants.

Moonvillage equivalent:
Use neighbor masks to choose inner corner, outer corner, concave corner, convex corner, cap, side, and filler roles. Tile IDs come from approved database classes, not variable-name trust.

### 5. Base ground fill happens after structural border work

DeepWoods rule:
`Build` places border/clearing/patch structure before `GenerateGround`. `PlaceTile` defaults to `DONT_OVERRIDE`, so late ground fill does not erase matrix edges.

Moonvillage equivalent:
Separate semantic terrain from rendering. Structural Back-layer transitions and border shadows must be protected from later base fill or decoration passes.

### 6. Ground variation is weighted and sparse

DeepWoods rule:
Grass groups have weighted variants. Common base tiles dominate; details appear with low weight.

Moonvillage equivalent:
Each design role should have at most four active variants. Use weights to avoid noisy maps, and store extra candidates as inactive alternatives.

### 7. Exits are protected visual structures

DeepWoods rule:
Rows skip `ExitRadius`; `GenerateExit` places forest side pieces, dark shadows, bright entry grass, and random end caps. Placement code later rejects exit/entry radius.

Moonvillage equivalent:
Dungeon ladders, maze gates, basement doors, and return warps should have protected capsules: walkable approach, readable visual frame, no decoration/monster collision.

### 8. Clearings are organic rooms

DeepWoods rule:
Lichtungen grow inward from side exits with a matrix that handles horizontal, vertical, steep, concave, and convex transitions.

Moonvillage equivalent:
Fairy groves, cursed plazas, and abandoned village squares should use organic boundary walkers rather than rectangular rooms.

### 9. Lakes use a separate edge system

DeepWoods rule:
Lake edges are animated tile matrices, then water tiles are marked with a `Water` property so later placement and monster logic can reject them.

Moonvillage equivalent:
Water, void pools, and swamp edges need their own approved transition class family and a collision/property pass. Until that exists, keep lake generation as a prototype-only feature.

### 10. Interior forest patches break empty space

DeepWoods rule:
Interior patches use free rectangles, shrink to fit, avoid world borders and occupied patches, then render the same matrix-style borders as the outer wall.

Moonvillage equivalent:
Use reserved rectangles for ruin blocks, tree islands, hedge clumps, and maze chunks. This prevents large flat spaces and gives navigation rhythm.

### 11. Clutter is placement-validated, not just sprinkled

DeepWoods rule:
Stuff placement shuffles candidates but checks blockedLocations, Buildings, border/exit/enter radius, water, footprint size, tree spacing, and clearing restrictions.

Moonvillage equivalent:
The map generator, monster spawner, forage spawner, decoration placer, and NPC path checker should share one placement validator.

### 12. Random counts use density budgets

DeepWoods rule:
Monsters, forest patches, lights, terrain features, and grass use area-based counts and density settings. Some use a two-dice distribution to avoid extremes.

Moonvillage equivalent:
Every generator family should have density knobs and performance caps: decoration density, monster density, path width, max empty area, light count, and protected radius.

### 13. Runtime maps need a safe lifecycle

DeepWoods rule:
`updateMap` creates a placeholder map, waits until network/seed/size are ready, avoids rebuilding when map ID matches, and sets the map ID when an override handles generation.

Moonvillage equivalent:
If Moonvillage uses runtime maps, the lifecycle must prevent null maps, repeated reloads, and half-built multiplayer locations.

### 14. External hooks are phase-aware

DeepWoods rule:
The API exposes before/after/override hooks by phase instead of one catch-all mutation point.

Moonvillage equivalent:
Provide hooks for semantic layout, base terrain, border resolve, transitions, placement, monsters, treasure, and validation so future quest/event systems can inject safely.
""".format(generated_at=GENERATED_AT)


DEEPWOODS_TILE_SKILL = """# DeepWoods Tile Definition Skill

- Generated: {generated_at}
- Sources inspected: `DeepWoodsTileDefinitions.cs`, `DeepWoodsBuilder.cs`, `DeepWoodsSettings.cs`, current Moonvillage style packs, and base-game resolution reports.

## The Pattern

DeepWoods does not scatter raw IDs through generation logic. It defines named groups and matrix objects, then builder methods consume the roles:

- scalar constants for special/debug/filler tiles;
- weighted arrays for base ground, dark ground, water, forest filler, and variants;
- row matrices for side borders;
- corner matrices for map corners;
- clearing matrices for organic bright grass and lake edges;
- helper methods that choose a tile by role and layer.

That pattern is safe to adopt. The raw tile IDs are not automatically safe to adopt.

## Important Safety Rule

DeepWoods variable names are code-context evidence, not intrinsic Stardew metadata. Moonvillage should trust this order of evidence:

1. Human-approved tile database usage profile.
2. Vanilla base-game authoritative metadata from unpacked `.tbin` maps.
3. Exact pixel duplicate of an approved anchor with matching usage profile.
4. Repeated Moonvillage/reference map usage evidence.
5. DeepWoods code role name as a design hint only.

Tile `946` remains quarantined for Buildings/wall/body/collision use. The base-game report says vanilla uses it dominantly on AlwaysFront with no intrinsic blocking property. It may later get an AlwaysFront canopy profile, but it must not be used as a wall body or blocker unless a future validator proves that specific profile.

## Useful Groups And Classification

| DeepWoods group | Role in DeepWoods | Moonvillage status | Reason |
| --- | --- | --- | --- |
| `GrassTiles.NORMAL` | common ground fill | safe vanilla metadata-backed when matched to approved DB | Base-game report says DeepWoods grass IDs now have authoritative `Type=Grass` evidence. |
| `GrassTiles.DARK` | dark ground near borders | safe as ground only when approved by DB/profile | Good shadow/blend concept; final IDs must come from approved ground/dark-ground profiles. |
| `GrassTiles.BRIGHT` | clearing and exit path material | partial | Some IDs are ground-like; edge/end roles still need transition profiles. |
| `PLAIN_FOREST_BACKGROUND = 946` | DeepWoods Buildings/filler context | do not use for Moonvillage wall body | Conflicts with vanilla/Moonvillage AlwaysFront evidence. Quarantine from collision. |
| `FOREST_BACKGROUND` | filler behind dense forest | needs human review | Contains 946 and other canopy/filler candidates; profile must define layer and collision separately. |
| `DeepWoodsRowTileMatrix` | side border caps, edges, dark/black grass | needs human review / design pattern safe | Matrix structure is excellent; IDs require approval by class/layer. |
| `DeepWoodsCornerTileMatrix` | corner geometry and shadow pieces | needs human review / design pattern safe | Adopt concave/convex role vocabulary, not raw IDs. |
| `DeepWoodsLichtungTileMatrix` | clearing edge and lake edge | partial | Bright clearing edge logic is useful; lake entries touch custom DeepWoods lake sheet context. |
| `WATER_TILES` | water body variants | needs base-game verification per tile | Water body can be approved through `Water=T`; edge/lily roles need separate profiles. |
| `WATER_LILY` | animated decoration | needs human review | Decorative/animated usage is not equivalent to water collision. |
| Debug constants | visual debugging | do not use in production | Useful only as tools-side marker tiles. |
| Infested/lake custom tilesheets | DeepWoods custom art | restricted custom asset dependency | Do not copy or depend on these unless separately licensed and credited. |

## Moonvillage File Pattern

Suggested future C# structure:

- `MoonTileDefinitions.cs`: approved symbolic tile/profile references only.
- `MoonTileGroups.cs`: weighted groups resolved from approved tile database keys.
- `MoonTileMatrices.cs`: row/corner/transition matrix roles by semantic class.
- `MoonGenerationStylePack.cs`: loads JSON style packs and validates max variants, layer rules, collision rules, risky tiles, and missing roles.

The generator should never ask for "tile 946". It should ask for `hedge_body_blocking`, `canopy_alwaysfront`, `dark_ground_under_wall`, or `grass_to_path_edge_N` and let the style pack resolve only approved candidates.

## Role Vocabulary To Carry Forward

- Ground: `ground_base`, `ground_variation`, `dark_ground`, `light_ground`.
- Border body: `blocking_body`, `front_cap`, `back_cap`, `side_edge`, `tall_overlay`.
- Corner: `inner_corner`, `outer_corner`, `concave_corner`, `convex_corner`.
- Transition: `edge_N/E/S/W`, `inner_corner_NE/NW/SE/SW`, `outer_corner_NE/NW/SE/SW`.
- Special: `exit_frame`, `entry_path`, `water_body`, `water_edge`, `decoration`, `light_marker`.

## Validator Requirements

- Reject tile 946 for Buildings/blocking roles.
- Require every style-pack tile to have an approved usage profile or be explicit `temporary_prototype_marker`.
- Enforce no more than four active variants per design role.
- Validate layer legality before TMX/runtime map output.
- Validate collision semantics separately per usage profile; multi-layer use is not a conflict if profiles are separate.
""".format(generated_at=GENERATED_AT)


MOON_TILE_MATRIX_DESIGN = """# Moon Tile Matrix Library Design

## Purpose

Create a Moonvillage matrix layer between semantic map generation and concrete tile IDs. This lets the generator place roles like `hedge_convex_corner_NE` without knowing which approved tile supplies that role.

## Proposed Files

- `MoonTileDefinitions.cs`
  - symbolic IDs for approved database keys;
  - no raw art assumptions;
  - optional prototype marker constants guarded by debug mode.
- `MoonTileGroups.cs`
  - weighted groups for ground, dark ground, path, wall body, canopy, decorations, water, ruin details;
  - active/inactive variants with max 4 active per design role.
- `MoonTileMatrices.cs`
  - `TerrainTransitionMatrix`;
  - `BorderRowMatrix`;
  - `BorderCornerMatrix`;
  - `ClearingMatrix`;
  - `WaterEdgeMatrix`;
  - `RuinWallMatrix`.
- `MoonGenerationStylePack.cs`
  - loads JSON;
  - resolves tile roles from approved profiles;
  - exposes marker fallback only for tools/debug generation.

## Core Data Shapes

```csharp
public sealed record MoonTileRef(
    string Role,
    string CandidateId,
    int? LocalTileId,
    string TilesheetKey,
    string[] AllowedLayers,
    string Collision,
    int Weight,
    bool Active);

public sealed record TerrainTransitionMatrix(
    Dictionary<Direction, MoonTileRef?> Edges,
    Dictionary<Corner, MoonTileRef?> InnerCorners,
    Dictionary<Corner, MoonTileRef?> OuterCorners,
    MoonTileRef? Fallback);

public sealed record BorderMatrix(
    Dictionary<Direction, MoonTileRef?> Body,
    Dictionary<Direction, MoonTileRef?> Front,
    Dictionary<Direction, MoonTileRef?> AlwaysFront,
    Dictionary<Corner, MoonTileRef?> Corners,
    Dictionary<Corner, MoonTileRef?> ConcaveCorners,
    Dictionary<Corner, MoonTileRef?> ConvexCorners,
    Dictionary<Direction, MoonTileRef?> DarkGround,
    IReadOnlyList<MoonTileRef> Fillers);
```

## Resolution Flow

1. Semantic generator marks cells: `grass`, `path`, `wall`, `water`, `ruin`, `exit`, `protected`.
2. Neighbor mask resolver classifies each cell role.
3. Matrix library maps role to tile candidates.
4. Approved-tile validator confirms layer/collision/source.
5. Tile placer writes the target layer or writes marker fallback in tools mode.
6. Final validator checks no missing required matrix roles remain.

## Quarantine Rules

- Tile 946 is allowed only as an unapproved/prototype marker for review or as a future approved AlwaysFront profile. It is never a wall body/blocker by default.
- DeepWoods custom image dependencies are not valid style-pack sources.
- A raw local tile ID without candidate/profile provenance is not valid for production.
"""


GAP_ANALYSIS = """# Moonvillage Generator Gap Analysis

- Generated: {generated_at}

## Current Moonvillage Tools State

The current tools-side generator already has useful pieces:

- semantic grid with entrance, exit, path, wall, grass/sand materials;
- route validation between entrance and exit;
- base Back fill;
- terrain transition markers for grass-to-sand;
- wall/body resolver with AlwaysFront markers;
- shadow/dark ground pass;
- decoration and light marker pass;
- TMX parse and tilesheet reference validation;
- quarantine for tile 946 as Buildings/wall body, using marker fallback instead.

This is structurally good, but it still reads like a test harness. DeepWoods shows the next jump: geometry-first generation with row/corner matrices, protected visual exits, footprint-aware placement, and density budgets.

## Critical Gaps

- Complete approved border matrix roles are missing: real wall body, top/front caps, AlwaysFront canopy edges, concave/convex corners.
- Terrain transition classes are missing for grass/path, grass/sand, grass/water, ruin/ground, hedge/path, and floor/wall.
- The style-pack schema is not formal enough to validate matrix completeness, active variant caps, risky tiles, or source restrictions.
- Tile 946 remains present in `moonvillage_forest_ruins.json` as a risky wall body entry and must stay quarantined until fixed.
- Interior wall/patch placement lacks a DeepWoods-style rectangle/footprint manager.
- Placement validation is not yet shared across generator, decoration, monsters, forage, and NPC paths.

## High-Priority Gaps

- Border generation still approximates bumping but does not yet use full row/corner matrix libraries.
- Exits are functionally open but not yet visually framed like protected structures.
- Ground variation lacks biome-specific spacing rules and max-empty-area controls.
- Decoration pass is too simple; it needs large-first, medium-second, small-last placement order.
- Water/lake generation is blocked on approved water-edge roles.
- Runtime xTile lifecycle has not been implemented for Moonvillage; current output is TMX prototype only.

## Medium-Priority Gaps

- Monster spawn planning exists only as design, not integrated with generated floors.
- Lighting has marker-style placeholders, not real style-pack light roles.
- Seasonal and quest-controlled variants need hook points.
- Generated map metadata should record every role-to-tile decision for review UI traceability.
- Validation should include max active variants per role and style-pack source policy every time.

## Low-Priority Gaps

- Animated tiles.
- Special first-level structures such as minecart equivalents.
- Randomized exit graph/lost behavior.
- Optional runtime API for third-party injection.

## Priority List

Critical:
- Build approved matrix role coverage and style-pack validation.
- Remove or quarantine tile 946 from wall/body/collision style-pack roles.
- Implement a proper border row/corner resolver with no-overwrite pass order.
- Implement shared placement validator.

High:
- Add rectangle/footprint space manager.
- Add protected visual exit capsules.
- Add density budgets and max-empty-area validation.
- Add richer ground variation and dark-ground border rhythm.

Medium:
- Add lake/water edge generation after approvals.
- Add monster spawn planner.
- Add hooks for quests/seasons/events.

Low:
- Add animated tile support and custom runtime-only effects.
""".format(generated_at=GENERATED_AT)


GENERATOR_DESIGN = """# Moonvillage DeepWoods-Inspired Generator Design

- Generated: {generated_at}

## What To Adopt

- Runtime-safe map lifecycle if/when generation moves into SMAPI.
- Semantic layout before tile placement.
- Corner-first, row-second border generation.
- Row bumping with max depth and end safety.
- Matrix role definitions for borders, corners, clearings, and transitions.
- Late non-overwrite base terrain fill.
- Protected exit capsules with visual framing.
- Area/density budgets.
- Shared blocked-location and footprint validator.
- Phase hooks with before/after/override semantics.

## What To Avoid

- Raw DeepWoods tile IDs as final Moonvillage truth.
- DeepWoods custom tilesheets or assets unless separately approved.
- Treating variable names as collision metadata.
- Letting tile 946 become a Buildings blocker.
- One giant random decoration pass.
- Final map generation before missing transition/wall/canopy roles are approved.

## Proposed Architecture

```text
MoonGeneratedMapRequest
  -> MoonGenerationConfig
  -> MoonStylePackLoader
  -> MoonSemanticLayoutBuilder
  -> MoonSpaceManager
  -> MoonLayerResolver
       -> TerrainTransitionResolver
       -> BorderMatrixResolver
       -> LayerPolicyValidator
  -> MoonPlacementValidator
  -> MoonDecorationSpawner
  -> MoonMonsterSpawner
  -> MoonMapValidator
  -> TMX/TMJ writer or runtime xTile map factory
```

## Class/File Layout

- `Generation/MoonGenerationConfig.cs`
- `Generation/MoonGeneratedMapRequest.cs`
- `Generation/MoonSemanticLayoutBuilder.cs`
- `Generation/MoonSpaceManager.cs`
- `Generation/MoonBorderGenerator.cs`
- `Generation/MoonTerrainTransitionResolver.cs`
- `Generation/MoonLayerResolver.cs`
- `Generation/MoonPlacementValidator.cs`
- `Generation/MoonAestheticPass.cs`
- `Generation/MoonMonsterSpawnPlanner.cs`
- `Generation/MoonMapValidator.cs`
- `Generation/MoonGenerationHooks.cs`
- `Data/MoonTileDefinitions.cs`
- `Data/MoonTileGroups.cs`
- `Data/MoonTileMatrices.cs`
- `Data/MoonGenerationStylePack.cs`

## Generation Phases

### Phase 1 - Semantic Layout

- Choose generator type: fairy forest, cursed ruins, void dungeon, maze, overgrown village.
- Set map bounds, entrance, exits, rooms, paths, protected zones, blocked zones, decoration zones.
- Reserve exit radius and path width before any wall/decor pass.

### Phase 2 - Base Terrain

- Fill only semantic ground classes.
- Use approved ground/floor/water/base profile groups.
- Keep base fill non-overwriting where structural Back-layer roles already exist.

### Phase 3 - Border And Wall Generation

- Create irregular outer border.
- Generate corners before rows.
- Apply bump-in/bump-out row walker.
- Use border matrices for body, front cap, side edge, corners, canopy overlays, and dark ground.

### Phase 4 - Transition Resolver

- Resolve grass/path, grass/water, floor/wall, ruin/ground, hedge/path, cliff/ground.
- Inspect N/E/S/W and diagonal neighbors.
- Place edge, inner corner, outer corner, concave, and convex roles.

### Phase 5 - Layer Resolver

- Back: ground, paths, water, shadows, terrain transitions.
- Buildings: blocking body only when an approved blocking profile exists.
- Front: low decorations, front caps, some wall faces.
- AlwaysFront: canopy, overhead cover, high wall tops.
- Paths: path data if needed for Stardew systems.

### Phase 6 - Aesthetic Pass

- Add dark ground near borders.
- Add weighted ground variation.
- Add sparse debris, mushrooms, flowers, rocks, ruin details, fairy lights, torches.
- Keep max active variants per role at 4.

### Phase 7 - Placement Pass

- Use blockedLocations and footprint reservations.
- Place large decorations first.
- Place medium decorations second.
- Place small details last.
- Preserve paths, exits, water, and protected zones.

### Phase 8 - Validation

- Walkability between required exits.
- Entrances and exits unblocked.
- No missing local tilesheets.
- No invalid TMX/TMJ.
- No restricted asset dependencies.
- No tile 946 blocker misuse.
- Every production tile has approved profile/layer/collision.
- No style-pack role exceeds four active variants.

## Connection To Tiled Map Assistant

The Tiled Map Assistant should provide:

- approved tile profiles from `tile_database_v1_human_approved.json`;
- candidate IDs and tilesheet provenance;
- exact duplicate approved anchors;
- style-pack role validation;
- missing matrix role reports;
- debug marker output for unapproved roles.

The generator should consume approved roles. It should not classify tiles during generation.
""".format(generated_at=GENERATED_AT)


PIPELINE_MD = """# Moonvillage Generation Pipeline

```text
Request(seed, generatorType, size, stylePack)
  |
  v
Config + approved tile database + style-pack schema validation
  |
  v
Semantic grid
  - bounds
  - paths
  - entrances/exits
  - rooms/patches
  - protected and blocked zones
  |
  v
Space manager
  - reserve exits
  - reserve patches/rooms
  - shrink or reject overlapping footprints
  |
  v
Layer resolver
  - Back base terrain
  - transition matrix
  - Buildings body/collision
  - Front caps/details
  - AlwaysFront canopy/overhead
  |
  v
Aesthetic pass
  - shadows
  - sparse variation
  - decorations
  - lights
  |
  v
Placement validator
  - large/medium/small objects
  - forage
  - monsters
  - NPC/path safety
  |
  v
Validation
  - walkability
  - layer legality
  - approved profiles
  - tilesheet refs
  - no restricted assets
  - no tile 946 blocker misuse
  |
  v
TMX/TMJ prototype or runtime xTile map
```

## Map Lifecycle

Tools-side:

1. Generate semantic grid.
2. Resolve layers into TMX/TMJ.
3. Write metadata and validation report.
4. Keep output under `tools/tiled-map-assistant/generated_maps/`.

Runtime later:

1. Create placeholder xTile map.
2. Wait for seed/network/config readiness.
3. Create real xTile map with loaded tilesheets.
4. Build layers.
5. Sort layers.
6. Add location to `Game1.locations`.
7. Validate warps and player positions.

## Data/Config Files

- `stylepacks/*.json`
- `stylepacks/stylepack_schema.json`
- `database/tile_database_v1_human_approved.json`
- `database/vanilla_authoritative_index.json` or generated equivalent
- `generated_maps/*.generation_metadata.json`
- `reports/missing_edge_tile_requirements.md`

## Future Implementation Missions

1. Build a formal style-pack validator.
2. Build MoonTileMatrix resolver from approved DB roles.
3. Replace raw GIDs in prototype style packs with candidate/profile references.
4. Implement DeepWoods-style border row/corner generator.
5. Implement shared placement validator.
6. Generate a new tools-side test map with real approved ground and marker-only missing roles.
7. Only after validation, design runtime SMAPI integration.
"""


STYLEPACK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://moonvillage.local/tiled-map-assistant/stylepack_schema.json",
    "title": "Moonvillage Tiled Map Assistant Style Pack",
    "type": "object",
    "x-moonvillageProjectPolicies": {
        "riskyTiles": [
            {
                "localTileId": 946,
                "reason": "Vanilla and Moonvillage evidence show dominant AlwaysFront/canopy-style use with no intrinsic blocking property.",
                "forbiddenRoles": ["wallBody", "Buildings", "blocker", "collision", "wall base", "hedge body"],
                "allowedOnlyWithProfiles": ["canopy_alwaysfront", "front_overlay"]
            }
        ],
        "maxActiveVariantsPerDesignRole": 4,
        "restrictedByDefault": ["deepwoods_custom_lake_tilesheet", "deepwoods_infested_outdoors_tilesheet", "deepwoods_exclusive_assets"]
    },
    "required": ["schemaVersion", "stylePackId", "tilesheet", "tileIdPolicy", "variantPolicy", "groups", "layerRules", "collisionRules", "densityRules", "spacingRules"],
    "properties": {
        "schemaVersion": {"type": "integer", "minimum": 2},
        "stylePackId": {"type": "string"},
        "description": {"type": "string"},
        "approvedDatabasePreferred": {"type": "boolean"},
        "tilesheet": {
            "type": "object",
            "required": ["name", "tileWidth", "tileHeight"],
            "properties": {
                "name": {"type": "string"},
                "firstgid": {"type": "integer", "minimum": 1},
                "source": {"type": "string"},
                "tileWidth": {"type": "integer", "const": 16},
                "tileHeight": {"type": "integer", "const": 16},
                "imageWidth": {"type": "integer", "minimum": 16},
                "imageHeight": {"type": "integer", "minimum": 16},
                "tileCount": {"type": "integer", "minimum": 1},
                "columns": {"type": "integer", "minimum": 1}
            }
        },
        "tileIdPolicy": {
            "type": "object",
            "properties": {
                "gidFormula": {"type": "string"},
                "markerMode": {"type": "boolean"},
                "markerFirstgid": {"type": "integer"},
                "markerTilesheet": {"type": "string"},
                "allowedSources": {"type": "array", "items": {"type": "string"}},
                "restrictedSources": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"}
            }
        },
        "variantPolicy": {
            "type": "object",
            "required": ["maxActiveVariantsPerDesignRole", "overflowBehavior"],
            "properties": {
                "maxActiveVariantsPerDesignRole": {"type": "integer", "maximum": 4},
                "overflowBehavior": {"enum": ["store_as_inactive_alternatives", "error"]},
                "activeSelectionOrder": {"type": "array", "items": {"type": "string"}}
            }
        },
        "markerTiles": {"type": "object", "additionalProperties": {"type": "integer"}},
        "terrainTransitions": {
            "type": "object",
            "properties": {
                "grass_to_sand": {"$ref": "#/$defs/transitionMatrix"},
                "grass_to_path": {"$ref": "#/$defs/transitionMatrix"},
                "grass_to_water": {"$ref": "#/$defs/transitionMatrix"},
                "floor_to_wall": {"$ref": "#/$defs/transitionMatrix"},
                "ruin_to_ground": {"$ref": "#/$defs/transitionMatrix"},
                "hedge_to_path": {"$ref": "#/$defs/transitionMatrix"},
                "cliff_to_ground": {"$ref": "#/$defs/transitionMatrix"}
            },
            "additionalProperties": {"$ref": "#/$defs/transitionMatrix"}
        },
        "borderMatrices": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "body": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "front": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "alwaysFront": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "darkGround": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "corners": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "concaveCorners": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "convexCorners": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "edgeMatrices": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "rowMatrices": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                    "fillers": {"type": "array", "items": {"$ref": "#/$defs/tileRef"}}
                }
            }
        },
        "groups": {
            "type": "object",
            "properties": {
                "groundBaseTiles": {"$ref": "#/$defs/tileGroup"},
                "groundVariationTiles": {"$ref": "#/$defs/tileGroup"},
                "darkGroundTiles": {"$ref": "#/$defs/tileGroup"},
                "lightGroundTiles": {"$ref": "#/$defs/tileGroup"},
                "pathTiles": {"$ref": "#/$defs/tileGroup"},
                "transitionTiles": {"$ref": "#/$defs/tileGroup"},
                "waterTiles": {"$ref": "#/$defs/tileGroup"},
                "waterEdgeTiles": {"$ref": "#/$defs/tileGroup"},
                "wallBodyTiles": {"$ref": "#/$defs/tileGroup"},
                "wallTopTiles": {"$ref": "#/$defs/tileGroup"},
                "wallSideTiles": {"$ref": "#/$defs/tileGroup"},
                "cornerMatrices": {"$ref": "#/$defs/tileGroup"},
                "edgeMatrices": {"$ref": "#/$defs/tileGroup"},
                "rowMatrices": {"$ref": "#/$defs/tileGroup"},
                "shadowTiles": {"$ref": "#/$defs/tileGroup"},
                "canopyOverlayTiles": {"$ref": "#/$defs/tileGroup"},
                "decorationTiles": {"$ref": "#/$defs/tileGroup"},
                "fillerTiles": {"$ref": "#/$defs/tileGroup"},
                "rareDecorationTiles": {"$ref": "#/$defs/tileGroup"},
                "torchTiles": {"$ref": "#/$defs/tileGroup"},
                "lightTiles": {"$ref": "#/$defs/tileGroup"},
                "ruinTiles": {"$ref": "#/$defs/tileGroup"},
                "natureDetailTiles": {"$ref": "#/$defs/tileGroup"},
                "forbiddenTiles": {"$ref": "#/$defs/tileGroup"},
                "riskyTiles": {"$ref": "#/$defs/riskyTiles"}
            },
            "additionalProperties": {"$ref": "#/$defs/tileGroup"}
        },
        "layerRules": {"type": "object", "additionalProperties": {"enum": ["Back", "Buildings", "Paths", "Front", "AlwaysFront"]}},
        "collisionRules": {"type": "object", "additionalProperties": {"type": "string"}},
        "densityRules": {
            "type": "object",
            "properties": {
                "groundVariationChance": {"type": "number", "minimum": 0, "maximum": 1},
                "decorationDensity": {"type": "number", "minimum": 0},
                "forageDensity": {"type": "number", "minimum": 0},
                "monsterDensity": {"type": "number", "minimum": 0},
                "lightDensity": {"type": "number", "minimum": 0},
                "borderBumpChance": {"type": "number", "minimum": 0, "maximum": 1},
                "borderBumpMaxDepth": {"type": "integer", "minimum": 0},
                "variationChance": {"type": "number", "minimum": 0, "maximum": 1}
            },
            "additionalProperties": True
        },
        "spacingRules": {
            "type": "object",
            "properties": {
                "protectedTileRadius": {"type": "integer", "minimum": 0},
                "minPathWidth": {"type": "integer", "minimum": 1},
                "maxEmptyAreaSize": {"type": "integer", "minimum": 1},
                "minDecorationSpacing": {"type": "integer", "minimum": 0},
                "minMonsterSpawnDistanceFromExit": {"type": "integer", "minimum": 0}
            },
            "additionalProperties": True
        }
    },
    "$defs": {
        "tileRef": {
            "oneOf": [
                {"type": "null"},
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "candidateId": {"type": "string"},
                        "profileId": {"type": "string"},
                        "gid": {"type": "integer"},
                        "localTileId": {"type": "integer"},
                        "source": {"type": "string"},
                        "weight": {"type": "number"},
                        "active": {"type": "boolean"},
                        "allowedLayers": {"type": "array", "items": {"enum": ["Back", "Buildings", "Paths", "Front", "AlwaysFront"]}},
                        "collision": {"type": "string"},
                        "notes": {"type": "string"}
                    }
                }
            ]
        },
        "tileGroup": {"type": "array", "items": {"$ref": "#/$defs/tileRef"}},
        "tileRole": {"$ref": "#/$defs/tileRef"},
        "transitionMatrix": {
            "type": "object",
            "properties": {
                "edges": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                "innerCorners": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                "outerCorners": {"type": "object", "additionalProperties": {"$ref": "#/$defs/tileRole"}},
                "fallback": {"$ref": "#/$defs/tileRole"}
            }
        },
        "riskyTiles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "localTileId": {"type": "integer"},
                    "reason": {"type": "string"},
                    "forbiddenRoles": {"type": "array", "items": {"type": "string"}},
                    "allowedOnlyWithProfiles": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }
}


SCHEMA_REPORT = """# Stylepack Schema Upgrade From DeepWoods

- Generated: {generated_at}
- Output schema: `tools/tiled-map-assistant/stylepacks/stylepack_schema.json`

## Why Upgrade

DeepWoods succeeds because tile choices are role-driven. The current Moonvillage style packs have useful groups, but they need formal structure for:

- terrain transition matrices;
- border row/corner matrices;
- separate Back/Buildings/Front/AlwaysFront rules;
- density and spacing controls;
- risky/forbidden tile policies;
- max 4 active variants per design role;
- approved database provenance.

## New Required Sections

- `terrainTransitions`
- `borderMatrices`
- `groups`
- `layerRules`
- `collisionRules`
- `densityRules`
- `spacingRules`
- `variantPolicy`
- `tileIdPolicy`

## Terrain Support

Style packs should provide:

- `groundBaseTiles`
- `groundVariationTiles`
- `darkGroundTiles`
- `lightGroundTiles`
- `pathTiles`
- `transitionTiles`
- `waterTiles`
- `waterEdgeTiles`

## Border/Wall Support

Style packs should provide:

- `wallBodyTiles`
- `wallTopTiles`
- `wallSideTiles`
- `cornerMatrices`
- `edgeMatrices`
- `rowMatrices`
- `shadowTiles`
- `canopyOverlayTiles`

## Aesthetic Support

Style packs should provide:

- `decorationTiles`
- `fillerTiles`
- `rareDecorationTiles`
- `torchTiles`
- `lightTiles`
- `ruinTiles`
- `natureDetailTiles`

## Safety Rules

- Production roles must resolve to approved candidate/profile references.
- Prototype raw GIDs are allowed only with marker/debug status.
- Tile 946 is a risky tile: forbid wall body, Buildings, blocker, collision, wall base, and hedge body unless a future explicit profile validates it.
- More than four active variants for one design role is a validation failure.
- DeepWoods custom asset sources are not allowed by default.

## Next Implementation Step

Build a validator that reads each style pack against this schema, then applies project-specific semantic checks not expressible in JSON Schema: tile 946 policy, approved profile lookup, restricted source policy, and active variant counting by design role.
""".format(generated_at=GENERATED_AT)


BORDER_PSEUDOCODE = """# DeepWoods-Style Border Generator Pseudocode

```text
function generate_border(semantic, config, style):
    reserve protected exit capsules

    corner_shapes = {}
    for corner in [NW, NE, SW, SE]:
        corner_shapes[corner] = walk_corner(
            start = map_corner(corner),
            width = random_between(minCorner, maxCorner),
            height = random_between(minCorner, maxCorner),
            matrix = style.borderMatrices.hedge_or_forest.corners
        )
        mark semantic cells as WALL
        record corner role per cell

    for side in [N, S, W, E]:
        row = side_span_between_corner_shapes(side, corner_shapes)
        exit_gaps = exits_on_side(side).expand(exitRadius)
        y_offset = 0
        last_step_was_bump_out = false

        for step in row:
            if step is inside exit_gaps:
                mark as EXIT_OPENING
                continue

            if can_bump_back(y_offset, step, row, last_step_was_bump_out):
                y_offset -= 1
                mark roles: concave_corner, convex_corner, dark_ground_edge
                last_step_was_bump_out = false
            else if can_bump_out(y_offset, step, row, config.borderBumpMaxDepth):
                y_offset += 1
                mark roles: convex_corner, concave_corner, dark_ground_edge
                last_step_was_bump_out = true
            else:
                mark roles: body, back_cap, front_cap, shadow
                last_step_was_bump_out = false

            fill cells behind protrusion as WALL_FILLER

    render border roles through BorderMatrixResolver
    validate:
        no protected exit blocked
        no missing required matrix roles in production mode
        no tile 946 blocker usage
```

## Notes

- Corners first, rows second.
- Semantic shape first, tile IDs second.
- `DONT_OVERRIDE` is the default; only matrix corrections can override.
- AlwaysFront overlay is emitted by the matrix resolver, not by decoration.
"""


AESTHETIC_PSEUDOCODE = """# DeepWoods-Style Aesthetic Pass Pseudocode

```text
function aesthetic_pass(map, semantic, style, validator, rng):
    dark_ground_budget = area * density.darkGroundNearBorders
    variation_budget = area * density.groundVariationChance
    decoration_budget = area * density.decorationDensity
    light_budget = area / density.tilesPerLight

    for each ground cell:
        if near wall/canopy and style has dark ground:
            place Back dark_ground role unless transition already exists
        else if rng chance ground variation:
            place Back ground_variation role

    empty_regions = find_large_empty_regions(semantic)
    for each region above maxEmptyAreaSize:
        add small nonblocking detail zones around edges
        leave central walk path intact

    candidate_cells = shuffled walkable cells

    place large decorations first:
        require footprint free
        require not in protected zone
        reserve footprint in blockedLocations

    place medium decorations second:
        require spacing from large objects
        require layer profile valid for Front or Buildings

    place small details last:
        require walkable or decorative collision
        avoid exits, path centerline, water, and NPC paths

    place lights:
        prefer exits, clearings, corners, and landmark zones
        cap by light budget

    validate:
        no decoration overwrote transitions
        no decoration blocked path
        variant count per design role <= 4
```
"""


PLACEMENT_PSEUDOCODE = """# DeepWoods-Style Blocked Placement Pseudocode

```text
class MoonPlacementValidator:
    blockedLocations = set()
    reservedRectangles = []

    function reserve_exit_capsules(exits, radius):
        for exit in exits:
            reserve diamond/rectangle around exit tile
            mark as protected

    function is_tile_free(x, y, profile):
        if out of bounds: return false
        if (x, y) in blockedLocations: return false
        if protected and profile.canBlockMovement: return false
        if Buildings layer has blocking tile: return false
        if Back tile has Water property and profile.disallowsWater: return false
        if semantic[x,y] in [wall, void, cliff] and profile.requiresWalkable: return false
        if tile is on required path centerline: return false
        return true

    function can_place_footprint(x, y, width, height, profile):
        for each covered cell:
            if not is_tile_free(cell, profile): return false
        return true

    function place_with_reservation(item, x, y, footprint, profile):
        if not can_place_footprint(...): return false
        write item/tile
        reserve all footprint cells
        return true

placement order:
    1. reserve exits, entrances, warp targets
    2. reserve main paths and NPC schedule paths
    3. place large objects
    4. place medium objects
    5. place small decoration
    6. place forage
    7. place monsters

monster placement:
    use same validator
    include monster bounding box footprint
    reject near exits unless event floor allows it
```
"""


LAYER_RESOLVER_PSEUDOCODE = """# DeepWoods-Style Layer Resolver Pseudocode

```text
function resolve_layers(semantic, style, approvedDb, markerMode):
    layers = empty Back, Buildings, Paths, Front, AlwaysFront

    function resolve_role(role, requiredLayer):
        candidates = style.get(role)
        candidates = filter active candidates
        candidates = filter approvedDb profile allows requiredLayer
        candidates = filter collision compatible with role
        candidates = reject risky tile policies, especially 946 blocker
        candidates = cap active variants to 4
        if one or more candidates:
            return weighted_pick(candidates)
        if markerMode:
            record missing role
            return marker_tile(role)
        fail validation

    pass 1: structural Back roles
        write protected path bases, water bodies, floor bases

    pass 2: terrain transitions
        for each cell:
            mask = inspect cardinal and diagonal neighbors
            role = terrain_role_from_mask(mask)
            if role:
                place Back resolve_role(role, Back)

    pass 3: border/body roles
        for each wall/hedge/forest cell:
            mask = inspect same-material neighbors
            bodyRole = border_body_role(mask)
            place Buildings resolve_role(bodyRole, Buildings)

    pass 4: front/cap roles
        for each wall/hedge/forest cell:
            frontRole = border_front_role(mask)
            if frontRole:
                place Front resolve_role(frontRole, Front)

    pass 5: AlwaysFront roles
        for each wall/hedge/forest cell:
            overlayRole = border_overlay_role(mask)
            place AlwaysFront resolve_role(overlayRole, AlwaysFront)

    pass 6: shadow/dark ground
        for each open ground adjacent to wall:
            place Back dark_ground_under_wall only if not transition-protected

    pass 7: decoration and lights
        use placement validator; never overwrite protected roles

    validate layers:
        Back has base terrain everywhere walkable
        Buildings only contains approved blocking/body profiles
        Front/AlwaysFront profiles match approved layers
        no missing production roles
```
"""


PROTOTYPE_SCRIPT = r'''#!/usr/bin/env python3
"""Tiny semantic-only DeepWoods-style map generation prototype.

This prototype writes debug output under this prototypes folder if run. It does
not create production maps and does not reference any art assets.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


WIDTH = 48
HEIGHT = 48


def in_bounds(x: int, y: int) -> bool:
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


def protected_tiles() -> set[tuple[int, int]]:
    result = set()
    for cx, cy in [(24, 46), (24, 1)]:
        for y in range(cy - 3, cy + 4):
            for x in range(cx - 3, cx + 4):
                if in_bounds(x, y):
                    result.add((x, y))
    return result


def generate(seed: int = 240614) -> tuple[list[list[str]], dict]:
    rng = random.Random(seed)
    grid = [["." for _ in range(WIDTH)] for _ in range(HEIGHT)]
    protected = protected_tiles()

    left = right = top = bottom = 3
    for y in range(HEIGHT):
        left = max(2, min(5, left + rng.choice([-1, 0, 0, 1])))
        right = max(2, min(5, right + rng.choice([-1, 0, 0, 1])))
        for x in range(left):
            grid[y][x] = "#"
        for x in range(WIDTH - right, WIDTH):
            grid[y][x] = "#"

    for x in range(WIDTH):
        top = max(2, min(5, top + rng.choice([-1, 0, 0, 1])))
        bottom = max(2, min(5, bottom + rng.choice([-1, 0, 0, 1])))
        for y in range(top):
            grid[y][x] = "#"
        for y in range(HEIGHT - bottom, HEIGHT):
            grid[y][x] = "#"

    x = 24
    for y in range(46, 0, -1):
        if y % 5 == 0:
            x = max(8, min(40, x + rng.choice([-1, 0, 1])))
        for dx in [-1, 0, 1]:
            if in_bounds(x + dx, y):
                grid[y][x + dx] = "+"

    for x, y in protected:
        grid[y][x] = "+"

    metadata = {
        "seed": seed,
        "legend": {
            ".": "open ground",
            "#": "wall/forest/hedge semantic cell",
            "+": "protected path/exit route"
        },
        "notes": [
            "Semantic-only prototype.",
            "No tile IDs, assets, TMX, or production map output."
        ]
    }
    return grid, metadata


def main() -> None:
    out_dir = Path(__file__).with_suffix("").parent / "deepwoods_style_map_generation_prototype_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    grid, metadata = generate()
    (out_dir / "semantic_grid_ascii.txt").write_text("\n".join("".join(row) for row in grid) + "\n", encoding="utf-8")
    (out_dir / "generation_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(out_dir)


if __name__ == "__main__":
    main()
'''


MASTER_REVIEW = """# DeepWoods Map Generation Master Review

- Generated: {generated_at}
- Source path: `tools/DeepWoodsMod-main`
- Scope: map generation skill for Moonvillage automated map maker.

## What DeepWoods Does Better

DeepWoods makes generated maps feel authored because it separates structure from rendering:

- it picks map size, entrance, exits, and clearing state before drawing;
- it creates a runtime xTile map with the Stardew layer stack;
- it generates borders using corner and row matrices;
- it uses bump-in/bump-out motion to avoid straight rectangles;
- it treats exits as protected visual structures;
- it fills base ground late so border details survive;
- it breaks large space with interior forest patches;
- it places stuff through blocked-location and footprint checks;
- it validates runtime lifecycle enough to avoid map reload crashes.

## Generation Passes To Adopt

- Constructor/entrypoint creates deterministic map state.
- `CreateSpace` equivalent selects generator mode, bounds, and entry.
- `DetermineExits` equivalent plans floor graph before art.
- Runtime map factory creates Back, Buildings, Front, Paths, AlwaysFront.
- Border generator creates corners first, rows second.
- Row walker applies bump-in/bump-out and fills behind protrusions.
- Transition resolver handles ground/path/water/ruin/wall edges.
- Placement validator protects exits, water, Buildings, and footprints.
- Monster planner uses area/depth/density and the same validator.

## Tile/Matrix Systems To Adopt

Adopt these concepts:

- named role constants;
- weighted tile groups;
- row matrices;
- corner matrices;
- clearing matrices;
- water/transition matrices;
- layer-aware placement helpers;
- no-overwrite by default with explicit override only when a matrix correction requires it.

Do not adopt raw DeepWoods IDs blindly. The approved tile database and vanilla authoritative metadata must own final tile identity.

## Placement Safety To Adopt

DeepWoods placement safety is simple and strong:

- shuffle candidates;
- reject blockedLocations;
- reject Buildings-layer cells;
- reject border/exit/enter radius;
- reject water;
- check full footprints for large objects;
- reserve footprint after placement;
- use the same blocked set for monsters.

Moonvillage should make this a shared `MoonPlacementValidator`, not duplicate it across systems.

## What To Avoid

- Copying DeepWoods custom image assets.
- Copying large source files wholesale.
- Treating tile 946 as Buildings/wall/body/blocker.
- Shipping marker-mode maps as production maps.
- Generating final maps before transition and border matrix classes are approved.
- Letting decoration overwrite transition or AlwaysFront border roles.

## Safe With Vanilla/Base-Game Metadata

The base-game metadata pass makes many vanilla ground, water, floor, passable, and blocker roles safe when candidate sheets are byte-identical and intrinsic properties match. This is the correct source for base terrain and collision decisions.

DeepWoods grass IDs that were confirmed by vanilla metadata can be used as approved ground roles. DeepWoods matrix IDs still need role-specific approval unless the approved database says otherwise.

## Restricted Or Needs Review

- DeepWoods custom lake and infested tilesheets.
- DeepWoods-exclusive terrain feature art.
- Any raw row/corner/canopy tile ID without approved layer profile.
- Tile 946 for any blocking/body role.
- Water/lake edge animations until approved water-edge profiles exist.

## Next Implementation Mission

1. Build style-pack validator from `stylepack_schema.json`.
2. Convert prototype style-pack raw GIDs to approved candidate/profile references where possible.
3. Remove or patch tile 946 from wallBodyTiles.
4. Implement `MoonSpaceManager` and DeepWoods-style border row/corner generator.
5. Implement shared `MoonPlacementValidator`.
6. Generate a new test map under `generated_maps/` with approved ground and marker-only unresolved roles.
7. Review missing matrix roles in the UI before any production map generation.
""".format(generated_at=GENERATED_AT)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROTOTYPES.mkdir(parents=True, exist_ok=True)
    STYLEPACKS.mkdir(parents=True, exist_ok=True)

    write_json(REPORTS / "deepwoods_generation_pass_map.json", {
        "generatedAt": GENERATED_AT,
        "scope": "DeepWoods map-generation mastery review for Moonvillage; reports/prototypes only.",
        "sourceRoot": "tools/DeepWoodsMod-main",
        "passes": PASS_MAP,
    })
    write(REPORTS / "deepwoods_generation_pass_map.md", pass_map_md())
    write(REPORTS / "deepwoods_aesthetic_rules.md", DEEPWOODS_AESTHETIC_RULES)
    write(REPORTS / "deepwoods_tile_definition_skill.md", DEEPWOODS_TILE_SKILL)
    write(REPORTS / "moonvillage_generator_gap_analysis.md", GAP_ANALYSIS)
    write(REPORTS / "moonvillage_deepwoods_inspired_generator_design.md", GENERATOR_DESIGN)
    write(REPORTS / "stylepack_schema_upgrade_from_deepwoods.md", SCHEMA_REPORT)
    write(REPORTS / "deepwoods_map_generation_master_review.md", MASTER_REVIEW)

    write(PROTOTYPES / "moon_tile_matrix_library_design.md", MOON_TILE_MATRIX_DESIGN)
    write(PROTOTYPES / "moonvillage_generation_pipeline.md", PIPELINE_MD)
    write(PROTOTYPES / "deepwoods_style_border_generator_pseudocode.md", BORDER_PSEUDOCODE)
    write(PROTOTYPES / "deepwoods_style_aesthetic_pass_pseudocode.md", AESTHETIC_PSEUDOCODE)
    write(PROTOTYPES / "deepwoods_style_blocked_placement_pseudocode.md", PLACEMENT_PSEUDOCODE)
    write(PROTOTYPES / "deepwoods_style_layer_resolver_pseudocode.md", LAYER_RESOLVER_PSEUDOCODE)
    write(PROTOTYPES / "deepwoods_style_map_generation_prototype.py", PROTOTYPE_SCRIPT)

    write_json(STYLEPACKS / "stylepack_schema.json", STYLEPACK_SCHEMA)

    print("Wrote DeepWoods mastery review reports and prototypes.")


if __name__ == "__main__":
    main()
