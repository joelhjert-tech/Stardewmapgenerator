# Joel-Approved Building Blocks — Summary

## Approved sheets found (6)
`review_corners_large`, `review_openings_large`, `review_shadow_and_front_overlay_large`,
`review_wall_body_large`, `review_wall_edges_large`, `review_wall_forward_lower_face_large`
— all detected via the `_approvedbyjoel` / `__approvedbyjoel` token. Floor and quarantined
sheets were **not** marked and stay unapproved.

## Block IDs mapped (no OCR)
176 sheet references → **174 unique blocks**, mapped by reusing the deterministic
`sheet_selections` that rendered the sheets. All 6 sheets mapped at **high confidence**.

## Promotion outcome (derived locked library)
| Lane | generatorStatus | count |
|---|---|--:|
| core_generator_safe | generator_ready | **144** |
| decoration_or_variant | prototype_ready | **29** |
| review_needed (opening) | review_needed | **1** |
| **Total promoted** | | **174** |
| Rejected / blocked | — | 0 (all 174 passed validation) |

- **Core generator-safe (144):** 40 lower-face, 39 wall_body, 31 inner_corner, 22 right_edge,
  9 outer_corner, 3 left_edge — clean structural blocks.
- **Decoration variants (29):** wall/corner blocks carrying ladders/objects/decoration —
  separated from core even though the sheet was visually approved (per the lane rules).
- **Review-needed (1):** a wall_body containing a ladder = plausible shaft socket; held back
  from core until socket geometry is confirmed.

## Floor deeper-review result (still unapproved)
436 floor blocks re-scored strictly: **11 clean_floor_base**, **134 clean_floor_variation**
(145 clean candidates), 251 floor_with_transition, 29 floor_with_decoration, 11
floor_wrongly_classified, 0 reject. **31 larger pure-floor samples re-cut** (5×5/7×7, 100%
floor). A focused `clean_floor_candidates_sheet.png` is ready; nothing approved.

## Quarantine deeper-analysis result (nothing moved)
155 quarantined blocks dispositioned: 92 reclassify_candidate (floor↔transition/edge), 33
propose_decoration_variant, 22 recut_larger_context, 6 remain_quarantined, 2
reject_permanently. No block left quarantine automatically.

## Enough core blocks for a test generator run?
**Yes.** 144 core generator-ready blocks now exist across walls, edges, corners and lower
faces — enough for a first end-to-end mine generator test (gated by wall-grammar conformance
+ out-of-bounds checks). The thinnest family is left edges (3); a future pass can mine more.

## Next recommended mission
1. **Wire the 144 core blocks into a gated test generator run** and validate the output with
   `validate_mine_wall_grammar_conformance.py` + `validate_out_of_bounds.py`.
2. **Floor approval**: if `clean_floor_candidates_sheet.png` looks right, mark it
   `_approvedbyjoel` and re-run this import to promote floors through the same lane.
3. **Second corpus**: extend the score→re-cut→clean→approve pipeline to Moonvillage Dungeon
   (.tmx), with a per-tilesheet tile-role model.
