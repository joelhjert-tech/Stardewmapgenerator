# Custom 12 — Joel Authored Runs Safety Status

| Guarantee | Status |
|---|---|
| Prototype only (no production map) | **confirmed** — `prototypeOnly: true`, `productionMapOutput: false`; output under `prototype_visual_maps/` only |
| Authored source pattern files untouched | **confirmed** — read-only; mtimes predate generation |
| Original Moonvillage maps untouched | **confirmed** |
| `mission_assets/**` untouched | **confirmed** |
| `unpacked_basegame/**` untouched | **confirmed** |
| Approved production DB unchanged | **confirmed** — `tile_database_v1_human_approved.json` mtime 2026-06-15 |
| Old block/template/canon DBs preserved | **confirmed** — none deleted or overwritten |
| Floor blocks not promoted/used | **confirmed** — `floor_mode: marker_floor_fallback`, flat placeholder |
| No loose single-tile structural placement | **confirmed** (validator: every structural placement is a complete run/block; markers write no tiles) |
| Decoration variants not used as core | **confirmed** — 4 decoration-variant runs excluded |
| No restricted external assets | **confirmed** — only the vanilla mine tilesheet is read |
| Old generator modes preserved | **confirmed** — default fresh mode regenerates custom_08 unchanged (36 fallbacks) |

## Structure sources
- Authored runs: `pattern_learning/joel_authored_runs_v1/joel_authored_runs_v1.json` (whole runs only).
- Secondary fill: `joel_approved_building_blocks_v1.locked.json` (locked, generator_ready).
- Canvas init: synthetic deep-void (pure void, not an authored asset). Floor: flat marker.

## Validators (all pass)
`validate_custom_12_joel_authored_runs.py`, `validate_joel_authored_runs_v1.py`,
`validate_custom_11_joel_block_output.py`, `validate_joel_building_block_approvals.py`,
`validate_cleaned_map_building_blocks.py`, `validate_mine_visual_canon.py`,
`validate_source_crop_remakes.py`, `validate_stylepacks.py`, `validate_approved_tags.py`,
`run_validation_tests.py` (88 tests).
