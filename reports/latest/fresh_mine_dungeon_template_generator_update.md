# Fresh Mine/Dungeon Template Generator Update

`build_smart_edge_wrapper_v2.py` consumes `mine_dungeon_fresh_template_library.json` and logs template/family placements for custom_08.

## Behavior

- Uses fresh template library and tile-ID families.
- Places complete template layer stacks only.
- Preserves deep-void initialization.
- Preserves lower-face extrusion through fresh `lower_face_3_tile_stack` templates.
- Uses explicit 8-way boundary classification.
- Logs selected template, selected tile-ID family, source cluster, written layer stack, and fallback cells.
- Does not place loose wall/top/corner/shadow tile IDs.

## Custom 08

- Output folder: `prototype_visual_maps/dungeon_review/custom_08_fresh_template_test/`
- Strict validator: PASS.
- Marker fallbacks: 98.
- Known visual gap: no generator-ready complete Front shadow template was learned, so Earth conformance fails on low `frontToBuildingsRatio`.
