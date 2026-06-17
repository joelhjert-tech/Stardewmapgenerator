# Fresh Mine/Dungeon Template Relearn Summary

- Maps inventoried: 79
- Unique repeated signatures: 95746
- Window occurrences scanned: 148519
- Tile-ID families created: 20
- Pattern clusters created: 6448
- Fresh templates created: 23
- Production maps generated: NO
- Source maps modified: NO

The fresh library preserves complete grids and layer stacks. Structural tile IDs remain forbidden as loose role-list placements.

## Evidence Retention

- Full scan unique signatures: 95,746.
- Retained representative signatures: recorded in `mine_dungeon_raw_windows.json`.
- Retention policy: top repeated signatures plus role/size representatives, so the database remains reviewable without storing every raw window.

## Custom 08 Result

- `custom_08_fresh_template_test` was generated from the fresh template library only.
- Strict fresh-template output validation: PASS.
- Base prototype validation: PASS.
- Earth vanilla visual-density conformance: FAIL on `frontToBuildingsRatio`.

This is an expected fail-closed outcome: the fresh relearn did not produce a complete generator-ready Front shadow / wall-overlay template that can be safely placed as a family. The v2 generator therefore refused to invent shadows from loose tile IDs. The structure is safer, but visually flatter than vanilla until shadow/front-overlay families are reviewed and promoted.
