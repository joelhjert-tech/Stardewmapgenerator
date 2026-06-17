# custom_09 Front Promotion Checkpoint — Before/After

- Date: 2026-06-16 · Generator: `build_custom_09_front_promotion_checkpoint.py` (updated Smart Edge-Wrapper v2).
- Scope: selection/promotion fix ONLY (no new mining). custom_08 preserved; custom_09 written to a new dir.

## Before / after ratio

| | Front tiles | Buildings tiles | frontToBuildingsRatio |
| --- | ---: | ---: | ---: |
| **custom_08** | 5 (torch markers only) | ~211 | **0.024** |
| **custom_09 checkpoint** | **122** (169 cells written) | 274 | **0.445** |
| Vanilla **earth** reference | — | — | p5 0.774 · p50 1.053 · p95 1.524 |
| Vanilla **global** reference | — | — | p5 0.060 · p50 0.905 |

**~18.7× improvement (0.024 → 0.445)** using only already-learned templates. The ratio now sits inside the *global* mine envelope (above global p5 0.060) but **below the earth p5 (0.774)** — earth mines are unusually shadow-heavy.

## Did the selection fix improve the ratio?

**Yes, substantially.** Root cause was not `items[0]`; it was (a) void-Front "templates" correctly rejected, (b) the complete `wall_top` template never being requested, (c) the `<2 structural cells` guard rejecting real-Front corners. All three are addressed (see `front_template_variant_selection_audit.md`).

## Front-bearing templates used

- `fresh_wall_top_3x1_a3ac51ac` — via the `wall_body → wall_top` remap (exposed north wall tops). Real Back 137 / Buildings 79 / Front 79.
- `fresh_upper_left_inner_corner_1x3_e386f75f` — real Front 216/232/213.
- `fresh_upper_right_inner_corner_1x3_ca0ce803` — real Front overlay.

## Front-bearing templates still skipped

- **0** real-Front templates skipped (`skippedFrontBearing = 0`).
- Correctly **excluded** (not real Front): `fresh_wall_body_3x1` and the two outer-corner templates carry only **void tile 77** on Front — promoting them would stamp void, so they remain marker-fallback candidates until real-Front variants are mined.

## Marker fallbacks

- custom_08: 98 → **custom_09: 36** (the wall_body→wall_top remap converted ~30 fallbacks into real placements).

## Visual notes

- Wall tops and the two upper inner corners now carry their vanilla Front overlay, so the map reads less flat than custom_08.
- Lower faces, left/right edges, outer corners, and ladder/shaft openings still have **no real Front overlay** (no such family learned yet) — these zones remain flat.
- Ladder opening still connected; entrance/exit reachable (validation PASS).

## Decision point

**Outcome B — ratio improved but still below the earth reference (0.445 vs 0.774).**
The selector fix succeeded and is the correct, complete-template-only behavior. To close the remaining gap to earth, the next mission should **mine the missing Front overlay families**: real lower-face shadow strips, left/right edge overlays, real outer-corner Front, and ladder/shaft opening overlays — from vanilla + Moonvillage dungeon maps, as complete Buildings+Front stacks. (If the target theme is global/frost rather than earth, custom_09 may already be in range — confirm the intended theme.)
