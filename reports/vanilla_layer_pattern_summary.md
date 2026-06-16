# Vanilla Layer Pattern Summary

- Generated: 2026-06-16T08:20:32+00:00
- Vanilla `.tbin` maps found: 255
- Vanilla maps parsed: 255
- Parse failures: 0

## Sources

- Vanilla maps: `tools/tiled-map-assistant/mission_assets/unpacked_basegame/*.tbin` read-only
- Vanilla metadata: `tools/tiled-map-assistant/review/auto_resolution/vanilla_authoritative_index.json`
- Approved profiles: `tools/tiled-map-assistant/database/tile_database_v1_human_approved.json`
- Map comparison catalog: `tools/tiled-map-assistant/database/map_catalog.json`
- Stylepack safety state: `tools/tiled-map-assistant/stylepacks/`

## Map Categories

- mine: 82
- farmhouse/interior: 69
- town exterior: 32
- festival: 22
- unknown: 11
- forest exterior: 11
- shop/interior: 9
- mountain exterior: 9
- special/event: 7
- beach exterior: 3

## Layer Findings

### Back

- Non-empty tiles: 463579
- Average density: 0.72553
- Usual meaning: ground/floor/water/base visual layer
- Collision expectation: walkable unless intrinsic water/special properties or Buildings blocks above
- Top coarse roles: approved_walkable_base (282839), intrinsic_water (80131), back_base_unknown (68838), intrinsic_typed_ground (21765), intrinsic_diggable_ground (9933)
- Top intrinsic properties: Type (320038), Spawnable (105489), Buildable (103482), CanPlantTrees (85552), Water (80131)
- Top approved classes: ground_base (279532), water_base (53979), floor_base (3307), collision_blocker (70), overlay (3)

### Buildings

- Non-empty tiles: 190080
- Average density: 0.38288
- Usual meaning: blocking structures, wall bodies, doors, furniture, structural boundaries
- Collision expectation: normally blocks movement unless a specific game rule overrides it
- Top coarse roles: building_layer_structure_or_object (180924), approved_walkable_base (7282), intrinsic_typed_ground (1074), intrinsic_water (496), approved_overlay_or_structure (238)
- Top intrinsic properties: Type (8109), Buildable (4975), Spawnable (4904), CanPlantTrees (4895), Passable (2895)
- Top approved classes: ground_base (6782), floor_base (500), canopy_overlay (387), water_base (359), overlay (238)

### Front

- Non-empty tiles: 68042
- Average density: 0.18983
- Usual meaning: front overlays, wall tops, signs, windows, upper furniture, decoration
- Collision expectation: drawn over base but should not be used as sole collision source
- Top coarse roles: front_overlay_or_decoration (66368), approved_walkable_base (1580), intrinsic_typed_ground (65), approved_overlay_or_structure (15), intrinsic_water (7)
- Top intrinsic properties: Type (1611), Spawnable (1352), Buildable (1231), CanPlantTrees (1231), NoSpawn (563)
- Top approved classes: ground_base (1575), overlay (15), collision_blocker (7), floor_base (5), water_base (5)

### AlwaysFront

- Non-empty tiles: 54833
- Average density: 0.14586
- Usual meaning: over-player canopy, roof, treetop, tall overlay
- Collision expectation: draw order only; collision should come from Buildings or base properties
- Top coarse roles: alwaysfront_overlay (49554), approved_overlay_or_structure (4988), approved_walkable_base (252), intrinsic_typed_ground (27), intrinsic_water (12)
- Top intrinsic properties: Passable (4988), Type (275), Spawnable (170), Buildable (130), CanPlantTrees (129)
- Top approved classes: overlay (4988), canopy_overlay (2787), ground_base (251), water_base (6), floor_base (1)

### Paths

- Non-empty tiles: 16494
- Average density: 0.0361
- Usual meaning: technical path/route layer
- Collision expectation: technical route data, not final visual collision by itself
- Top coarse roles: technical_path_marker (16485), approved_walkable_base (9)
- Top intrinsic properties: GreenRain (367), PathType (355), Spawnable (9), Type (9), Buildable (3)
- Top approved classes: ground_base (9)

## Most Common Layer Stacks

- `Back`: 228578 cells, role `base_ground_floor_or_water`
- `Back+Buildings`: 124386 cells, role `blocking_structure_or_object`
- `empty`: 119865 cells, role `empty_stack`
- `Back+Buildings+Front`: 24952 cells, role `blocked_structure_with_front_overlay`
- `Back+AlwaysFront`: 21680 cells, role `overhead_overlay_collision_from_lower_layers`
- `Back+Front`: 21348 cells, role `front_decoration_or_overlay`
- `Back+Buildings+AlwaysFront`: 19045 cells, role `blocked_structure_with_overhead_overlay`
- `Back+Paths`: 13696 cells, role `technical_path_over_base`
- `Buildings`: 12431 cells, role `blocking_structure_or_object`
- `Front`: 9857 cells, role `front_decoration_or_overlay`
- `Back+Buildings+Front+AlwaysFront`: 4233 cells, role `blocked_structure_with_front_overlay`
- `Back+Front+AlwaysFront`: 4047 cells, role `overhead_overlay_collision_from_lower_layers`

## Tile 946 Note

- Vanilla tile 946 observations captured: 40
- This mission preserves the existing quarantine: tile 946 is not approved as Buildings/wall/body/blocker.
