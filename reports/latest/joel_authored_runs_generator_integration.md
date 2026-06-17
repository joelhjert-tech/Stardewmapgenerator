# Joel Authored Runs — Generator Integration

## New mode
`python build_smart_edge_wrapper_v2.py --run-source joel-authored-v1`

Loads `pattern_learning/joel_authored_runs_v1/joel_authored_runs_v1.json` and places **whole
authored runs** as structures. Old modes (`--template-source fresh-relearn|visual-canon-v1`,
`--block-source joel-approved-v1`) and the marker fallback are all preserved unchanged
(verified: default fresh mode still emits custom_08 with 36 fallbacks).

## Placement priority (implemented)
1. **Joel-authored run** (priority 0) — complete authored structure if it fits the boundary context.
2. **Joel-approved locked block** (priority 1) — secondary fill for roles/cells a run can't cover.
3. **Marker fallback** — only if neither fits; never a loose tile.

Each boundary cell tries candidates in this order (`_attempt_template` per candidate); the
first that passes preflight (in-bounds, no Buildings-over-floor) is stamped. Runs are anchored
at their floor-contact cell so the run body extends into the void (building up multi-row walls),
never onto floor.

## Rules honored
- Complete runs only — never split into loose tiles (`allowTrimming:false`, `allowRepeating:false`).
- Runs are chosen smallest-fitting-first within their priority for deterministic, low-overlap placement.
- Decoration-variant runs (review_needed) are **excluded** from core structure.
- A run that doesn't fit falls through to a block, then a marker — fail-closed, all reported.

## Role mapping (content-based, not layer name)
Runs are keyed to generator boundary roles by their floor-contact geometry:
- top-wall runs → `lower_face_3_tile_stack` (player-facing wall face; body extends up as the cap)
- side runs → `left_wall_edge` / `right_wall_edge`
- corners → oriented inner/outer corner roles
- ladder entrance → placed where lower-face context matches

## Not yet wired (documented gaps)
- The full 6-level cascade (run→block→canon→fresh→marker) currently implements levels 1, 2, 5.
  Canon/fresh fallback for run mode is a future enhancement.
- The generator still places per **boundary cell**; large runs that would ideally tile a whole
  edge region are placed where their contact cell matches. A **run-region placement** pass
  (place one run per contiguous boundary segment) is the next structural improvement and would
  cut the remaining `floor_to_wall_transition` / top-edge markers.
