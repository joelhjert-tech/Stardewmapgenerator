# 3x3 Layer Grammar Learning Summary

- Generated: 2026-06-16T08:20:32+00:00
- Vanilla maps parsed: 255/255
- Structural 3x3 patterns observed: 286943
- Structural 3x3 patterns written: 2000
- Decoration/support 3x3 patterns observed: 92410
- Decoration/support 3x3 patterns written: 2000

## What Changed

- The learner now records 3x3 neighborhoods instead of relying only on one coordinate's vertical layer stack.
- Strict structure is separated from decoration: `Back` + `Buildings` form structural templates, while `Front`, `AlwaysFront`, and `Paths` form looser support/placement evidence.
- Empty cells are preserved as constraints, so clear space in front of walls, doors, paths, and supports can be learned instead of ignored.
- Tile properties are carried into grammar evidence from vanilla metadata and tBIN per-placement properties where available.

## Outputs

- `pattern_learning/vanilla/vanilla_3x3_neighborhood_patterns.json`
- `pattern_learning/layer_combinations/structural_3x3_grammar_patterns.json`
- `pattern_learning/layer_combinations/decoration_placement_rules.json`
- `pattern_learning/layer_combinations/empty_cell_constraints.json`
- `pattern_learning/layer_combinations/tile_property_requirements.json`

## Strong Structural Templates

- `dab89bbec445` count 4440: center `Back=mine:138|Buildings=mine:77`
- `516d779ced8c` count 1782: center `Back=elliottseatiles:24|Buildings=empty`
- `c84529002172` count 1687: center `Back=island_tilesheet_1:320|Buildings=empty`
- `04507f1580fa` count 1448: center `Back=summer_beach:75|Buildings=empty`
- `cbd324b2d3a6` count 1346: center `Back=spring_island_tilesheet_1:674|Buildings=empty`
- `c73710d9b7de` count 1050: center `Back=island_tilesheet_1:135|Buildings=empty`
- `634f52d0b7a0` count 1022: center `Back=island_tilesheet_1:199|Buildings=empty`
- `3edcadd93d74` count 817: center `Back=mine:77|Buildings=empty`

## Common Decoration Support Rules

- Count 3362: center `Back=empty|Buildings=empty|Front=mine:77|AlwaysFront=out_of_bounds|Paths=out_of_bounds`
- Count 3141: center `Back=empty|Buildings=empty|Front=empty|AlwaysFront=island_tilesheet_1:17|Paths=empty`
- Count 1370: center `Back=empty|Buildings=empty|Front=mine_dark:77|AlwaysFront=out_of_bounds|Paths=out_of_bounds`
- Count 1026: center `Back=empty|Buildings=empty|Front=empty|AlwaysFront=empty|Paths=volcano_dungeon:331`
- Count 933: center `Back=empty|Buildings=empty|Front=towninterior:0|AlwaysFront=out_of_bounds|Paths=empty`
- Count 699: center `Back=spring_outdoorstilesheet:587|Buildings=empty|Front=empty|AlwaysFront=empty|Paths=paths:22`
- Count 684: center `Back=spring_outdoorstilesheet:587|Buildings=empty|Front=empty|AlwaysFront=empty|Paths=paths:13`
- Count 621: center `Back=mine:138|Buildings=empty|Front=mine:214|AlwaysFront=out_of_bounds|Paths=out_of_bounds`

## Property Grammar Examples

- `structural` C Back: `Type=Grass` observed 143440 times
- `structural` E Back: `Type=Grass` observed 141722 times
- `structural` W Back: `Type=Grass` observed 141654 times
- `structural` N Back: `Type=Grass` observed 141640 times
- `structural` S Back: `Type=Grass` observed 140884 times
- `structural` NE Back: `Type=Grass` observed 139966 times
- `structural` NW Back: `Type=Grass` observed 139889 times
- `structural` SE Back: `Type=Grass` observed 139202 times
- `structural` SW Back: `Type=Grass` observed 139152 times
- `structural` C Back: `Buildable=T` observed 102324 times
- `decoration` S Back: `Type=Grass` observed 52342 times
- `decoration` C Back: `Type=Grass` observed 51763 times
- `decoration` SW Back: `Type=Grass` observed 50986 times
- `decoration` SE Back: `Type=Grass` observed 50777 times
- `decoration` W Back: `Type=Grass` observed 50627 times
- `decoration` E Back: `Type=Grass` observed 50290 times
- `decoration` N Back: `Type=Grass` observed 48902 times
- `decoration` NW Back: `Type=Grass` observed 47913 times
- `decoration` NE Back: `Type=Grass` observed 47397 times
- `decoration` C Back: `Buildable=T` observed 34969 times

## Generator Implications

- Mine walls, cliffs, water edges, and path transitions should be selected from whole 3x3 structural templates or approved safe patterns, not from isolated tile IDs.
- Decorations should be placed after structure and should validate support ground, lower-layer blocking state, and overlay/collision rules.
- Empty `Buildings` cells can be mandatory clearances. Future generators should treat them as positive rules.
- Visual water/path/special tiles must keep their learned properties when exported, or they can look right but play wrong.
