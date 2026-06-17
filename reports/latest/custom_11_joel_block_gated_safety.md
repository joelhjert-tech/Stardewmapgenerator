# Custom 11 — Joel Block Gated Test Safety Status

| Guarantee | Status |
|---|---|
| Prototype only (no production map) | **confirmed** — `prototypeOnly: true`, `productionMapOutput: false`; output under `prototype_visual_maps/` only |
| Original Moonvillage maps untouched | **confirmed** |
| `mission_assets/**` untouched | **confirmed** — source mine maps read-only (mtime predates generation) |
| `unpacked_basegame/**` untouched | **confirmed** |
| Approved production DB unchanged | **confirmed** — `tile_database_v1_human_approved.json` mtime 2026-06-15 |
| Floor blocks not promoted/used | **confirmed** — `floor_mode: marker_floor_fallback`, `unapprovedFloorBlocksUsed: 0` |
| Quarantined blocks not used | **confirmed** (validator check) |
| Decoration variants not used as core | **confirmed** — 29 skipped |
| Review-needed openings not used as core | **confirmed** — 1 skipped |
| No loose single-tile structural placement | **confirmed** — every structural cell belongs to a whole block; markers write no tiles |
| Old generator behavior preserved | **confirmed** — default `--template-source fresh-relearn` regenerates custom_08 unchanged (Front/Buildings ≈ 0.45) |

## Structure source
Core structure loaded **only** from
`pattern_learning/map_building_blocks/cleaned_blocks/joel_approved_building_blocks_v1.locked.json`,
filtered to `visualStatus=Joel_approved` + `generatorStatus=generator_ready` + `locked=true`.
A synthetic deep-void fill (pure void, not a Joel block) initializes the canvas; floors use a
flat marker placeholder. No fresh/canon template and no loose tile is used for structure in
this mode.

## Validators (all pass)
`validate_custom_11_joel_block_output.py` (16 checks), `validate_joel_building_block_approvals.py`
(174/174), `validate_cleaned_map_building_blocks.py`, `validate_map_building_blocks.py`,
`validate_mine_visual_canon.py`, `validate_source_crop_remakes.py`, `validate_stylepacks.py`,
`validate_approved_tags.py`, `run_validation_tests.py` (88 tests).
