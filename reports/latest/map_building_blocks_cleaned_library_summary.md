# Map Building Blocks — Cleaned Library Summary (mines)

- Original blocks scored: **931**
- Kept for review (clean as-is): **516**
- Re-cut for review (larger context): **260**
- Quarantined: **155**
- Cleaned library total (review-ready candidates): **776**

## Decision by block type

| blockType | keep | recut | quarantine |
|---|--:|--:|--:|
| mine_blocked_boundary | 0 | 0 | 8 |
| mine_floor_base | 142 | 0 | 59 |
| mine_floor_variation | 175 | 0 | 60 |
| mine_inner_corner | 68 | 0 | 4 |
| mine_outer_corner | 0 | 27 | 4 |
| mine_wall_body | 22 | 197 | 15 |
| mine_wall_forward_lower_face | 84 | 36 | 2 |
| mine_wall_left_edge | 3 | 0 | 0 |
| mine_wall_right_edge | 22 | 0 | 3 |

## Top quarantine reasons

- 51 — below the type quality bar: floor block clips wall cells (not pure floor)
- 43 — misclassified: geometry does not match block type
- 20 — forbidden contamination: contains ladder/object/light
- 19 — cropped; re-cut could not resolve the structure (needs larger/variable context)
- 9 — forbidden contamination: non-shadow Front decoration
- 7 — below the type quality bar: reusable-generator score below threshold
- 3 — below the type quality bar: edge block carries too much void
- 3 — below the type quality bar: floor block contains void

## Best candidates by family (by reusableGeneratorScore)

**Floor**
- `mbb_mine_floor_base_3x3_c5d66dd774696523` (mine_floor_base, 3x3, reuse=1.00, freq=4768)
- `mbb_mine_floor_base_5x5_38ac065b67b22156` (mine_floor_base, 5x5, reuse=1.00, freq=1809)
- `mbb_mine_floor_base_3x3_e82699b20545967f` (mine_floor_base, 3x3, reuse=1.00, freq=82)
- `mbb_mine_floor_base_3x3_82f8f179d921e3b9` (mine_floor_base, 3x3, reuse=1.00, freq=65)
- `mbb_mine_floor_base_3x3_4d010161121e2848` (mine_floor_base, 3x3, reuse=1.00, freq=58)

**Wall**
- `mbb_mine_wall_body_3x3_9bbdf20b581ede02__rc7x7_49420d8e6f5ac2da` (mine_wall_body, 7x7, reuse=0.97, freq=5)
- `mbb_mine_wall_body_3x3_4d4860061bf0b99c__rc7x7_311956047fb4adfc` (mine_wall_body, 7x7, reuse=0.97, freq=8)
- `mbb_mine_wall_body_3x3_4139c7e95562ecb2__rc7x7_e4b3c8a13a99d037` (mine_wall_body, 7x7, reuse=0.97, freq=6)
- `mbb_mine_wall_body_3x3_8ea3eee3fc64ea8e__rc7x7_fddd746df8663680` (mine_wall_body, 7x7, reuse=0.97, freq=5)
- `mbb_mine_wall_body_3x3_c70906e3a6146902__rc7x7_70dea89eb7f9acfe` (mine_wall_body, 7x7, reuse=0.97, freq=4)

**Edge**
- `mbb_mine_wall_right_edge_3x3_4401e3d6d315d1e9` (mine_wall_right_edge, 3x3, reuse=1.00, freq=11)
- `mbb_mine_wall_right_edge_3x3_e4b89215d0b9c075` (mine_wall_right_edge, 3x3, reuse=1.00, freq=10)
- `mbb_mine_wall_right_edge_3x3_79156df36e6219f6` (mine_wall_right_edge, 3x3, reuse=1.00, freq=10)
- `mbb_mine_wall_right_edge_3x3_5b6f9c632108aa83` (mine_wall_right_edge, 3x3, reuse=1.00, freq=9)
- `mbb_mine_wall_left_edge_3x3_af1c44e450cead29` (mine_wall_left_edge, 3x3, reuse=1.00, freq=8)

**Corner**
- `mbb_mine_inner_corner_3x3_c1fd0830dea523e7` (mine_inner_corner, 3x3, reuse=1.00, freq=22)
- `mbb_mine_inner_corner_3x3_b59cd46b5b084be2` (mine_inner_corner, 3x3, reuse=1.00, freq=22)
- `mbb_mine_inner_corner_3x3_4333051771171056` (mine_inner_corner, 3x3, reuse=1.00, freq=18)
- `mbb_mine_inner_corner_3x3_7f1da0ff1218e166` (mine_inner_corner, 3x3, reuse=1.00, freq=17)
- `mbb_mine_inner_corner_3x3_6068a7871aec6204` (mine_inner_corner, 3x3, reuse=1.00, freq=15)
