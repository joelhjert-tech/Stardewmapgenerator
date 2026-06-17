# Custom 11 — Joel-Approved Block Gated Test Summary

First gated mine prototype rendered with **only locked Joel-approved building blocks** for
core structure. Output: `prototype_visual_maps/dungeon_review/custom_11_joel_block_gated_test/`.
Validation: **PASS** (prototype-only).

Run: `python build_smart_edge_wrapper_v2.py --block-source joel-approved-v1`

## Approved blocks used (104 placements, all locked + generator_ready)
| block type | placements |
|---|--:|
| mine_wall_forward_lower_face | 29 |
| mine_inner_corner | 24 |
| mine_wall_right_edge | 22 |
| mine_wall_left_edge | 16 |
| mine_outer_corner | 13 |

By generator role: left_wall_edge 16, right_wall_edge 22, lower_face 29, lower_left_inner 15,
lower_right_inner 9, upper_left_outer 6, upper_right_outer 7. (Selection is deterministic
smallest-footprint-first, so a small set of distinct blocks is reused across the perimeter.)

## Block types missing / not consumed → marker fallback (221 cells)
- **wall_body (exposed north top): 30** — no `mine_wall_back_top_edge` blocks were approved.
- **floor_to_wall_transition: 63** — no such block type exists.
- **Missing corner orientations:** upper_right_inner (17), lower_right_outer (16),
  lower_left_outer (14), upper_left_inner (15) — those orientations had no approved block.
- **ladder_opening: 1** — openings are review-needed, excluded from core.
- ambiguous boundaries: 4; plus a few lower_face/inner-corner cells that failed placement
  preflight (block overlapped floor).
- **39 interior `mine_wall_body` blocks** are approved but **not consumed** by the edge-wrapper
  (it deep-void-fills interiors); they would feed a future region-fill generator.

## Floor mode
**marker_floor_fallback** — flat placeholder floor (tile 138, no variation). Floor blocks are
**not** approved yet (their sheet was not marked `_approvedbyjoel`), so no floor block was
promoted or used. `unapprovedFloorBlocksUsed: 0`.

## Does it look better than custom_09?
Mixed, and honestly so:
- **Trust/safety: better.** Every structural cell is a human-approved, locked, validated mine
  block — no fresh/unreviewed templates. The perimeter walls, lower faces and corners read as
  real mine structure.
- **Coverage/density: worse right now.** custom_09 (fresh templates) had a Front/Buildings
  ratio ≈ 0.45 and only 36 fallbacks; custom_11 is ≈ 0.014 with 221 fallbacks, because the
  approved set lacks top-edge, several corner orientations, transitions and Front-bearing
  shadow blocks. Top edges and missing corners are clearly-marked markers.
- See `before_after_custom_09_vs_custom_11.png` and `block_overlay.png`.

## Enough approved structure for further testing?
**Yes for a gated perimeter test** (edges, lower faces, most inner corners, two outer-corner
orientations place correctly). **Not yet for a full dense mine**: it needs top-edge/wall_top
blocks, the missing corner orientations, Front-shadow pairing, and approved floors.

## Next recommended manual review step
Approve the **floor candidates** (`deeper_floor_review/clean_floor_candidates_sheet.png`) and a
**back-top-edge / wall_top** sheet, then re-run this gated test — that closes the two biggest
fallback sources (floor + north tops). See `custom_11_next_floor_review_plan.md`.
