# Custom 12 — Joel Authored Runs Test Summary

Prototype mine rendered with **Joel-authored runs (priority) + Joel-approved blocks** for
structure. Output: `prototype_visual_maps/dungeon_review/custom_12_joel_authored_runs_test/`.
Validation: **PASS** (prototype-only).

Run: `python build_smart_edge_wrapper_v2.py --run-source joel-authored-v1`

## Source corpus
- Authored folders discovered: `Joel_custompatterns/` (batch 1) + `Joel_custompatterns/Patter_2/` (batch 2).
- Authored patterns parsed: **27** (10 + 17). Reference maps parsed: **2**
  (`refrencemapmines1.tmx` 20×20, `refrensmap2.tmx` 35×33).
- Run library: **27 runs** (`joel_authored_runs_v1`), 23 core + 4 decoration variants.

## Placement outcome
| source | placements |
|---|--:|
| **Joel-authored runs** (priority 1) | **47** |
| Joel-approved blocks (priority 2) | 85 |
| Marker fallback (priority 3) | 193 |
| **Structural total** | **132** |

Wall cells: **484** (custom_11 had 345). Run types placed: ladder_entrance 20, left_wall_run 9,
lower_face_soft_curve 9, lower_face_run 3, inner_corner 4, hard_corner 1, soft_corner 1.

## Coverage
- **Top-wall:** authored top-wall runs available and placed via the lower-face contact role
  (their body extends up into the void as multi-row caps) — the role that was 100% marker in custom_11.
- **Lower-face:** authored lower-face + soft-curve runs (29 placements by role).
- **Side walls:** left (10) / right (3) edge placements from authored runs, blocks as fill.
- **Corners/bends:** authored hard/soft/inner corners + outer-corner runs; blocks fill remaining orientations.
- **Ladder entrance:** authored ladder-entrance run placed (20×) where lower-face context matched.

## Visual improvement
- **vs custom_09 (fresh templates):** see `before_after_custom_09_vs_custom_12.png`. custom_12 is
  human-authored structure (higher trust); fresh had denser Front shadow but unreviewed art.
- **vs custom_11 (Joel blocks):** see `before_after_custom_11_vs_custom_12.png`. custom_12 has
  **+139 wall cells** and visibly thicker, more complete walls — the authored runs build up
  multi-row walls where blocks gave single-row edges.

## Remaining fallbacks (193)
floor_to_wall_transition 63, wall_body (south-edge tops) 30, missing corner orientations
(upper_right_inner 17, lower_right_outer 16, upper_left_inner 15, lower_left_outer 14),
lower_face overflow 26, ambiguous 4, ladder_opening 1. See `custom_12_next_gaps.md`.

## Enough for further testing?
Yes — runs now drive top/lower/side/corner/ladder structure with a clean run→block→marker
cascade. The dominant remaining gap is **per-cell placement of large runs**; a run-region
placement pass is the next step.
