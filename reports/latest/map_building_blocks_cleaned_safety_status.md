# Map Building Blocks — Cleaned Safety Status (mines)

## Protected areas — untouched

| Protected area | Status |
|---|---|
| Approved production DB (`database/tile_database_v1_human_approved.json`) | **unchanged** (mtime 2026-06-15, no write this pass) |
| `mission_assets/**` (incl. `unpacked_basegame/Mine` source maps) | **read-only** — parsed, never written |
| `unpacked_basegame/**` base-game files | **read-only** |
| Original Moonvillage maps | **not modified** |
| Original block library (`building_block_library.json`) | **preserved** beside cleaned outputs |
| Production maps | **none generated** |

All new artifacts are written under
`pattern_learning/map_building_blocks/cleaned_blocks/` and `reports/` only. The single
tilesheet image read is `prototype_visual_maps/dungeon_review/tilesheets/mine.png`.

> Note: a Moonvillage dungeon `.tmx` carries a 2026-06-16 mtime, but that predates this
> cleaning session and was not written by any script here — this pass touches only
> `unpacked_basegame/Mine` and that read-only.

## Promotion safety

- No block is `generator_ready`. Every cleaned/re-cut block is `visualStatus: proposed`,
  `generatorStatus: review_needed`, `locked: false`.
- Approval packs ship with `decision: null`; nothing is pre-decided.
- Quarantined blocks cannot leak into approval packs (validated).
- Re-cutting never writes to a source map — it re-reads the original `.tbin` and captures a
  larger window in memory.

## Validation

| Validator | Result |
|---|---|
| `validate_cleaned_map_building_blocks.py` | **PASS** (0 errors) |
| `validate_map_building_blocks.py` | **PASS** (0 errors) |
| `validate_stylepacks.py` | **PASS** (0 errors, 4 pre-existing warnings) |
| `validate_approved_tags.py` | **PASS** (0 errors, 0 warnings) |
| `run_validation_tests.py` | **OK** (88 tests) |

## Negative rules still in force
- No loose structural tile placement (whole blocks only).
- Front-overlay-only blocks require their paired wall base.
- Void (77/135) is never floor/wall art.
- Tile 946 remains canopy-only (out of scope for the mine pass).
- Singletons (freq < 4 / maps < 3) stay quarantined, never generator_ready.
