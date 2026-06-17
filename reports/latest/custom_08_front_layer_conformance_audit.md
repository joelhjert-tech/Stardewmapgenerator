# custom_08 Front-Layer Conformance Audit

- Date: 2026-06-16 · Read-only audit (Task 1). No files modified, no maps generated.
- Inputs inspected: custom_08 TMX/metadata/validation + placement/family/edge debug JSON, fresh template library, tile-ID families, Smart Edge-Wrapper v2 code, vanilla envelope baseline.

## Verdict

custom_08 fails the **earth** `frontToBuildingsRatio` gate, and the root cause is **not** missing data. It is a **template-selection bug**: the fresh library already contains 6 Front-bearing templates, but the generator never places their Front cells. Front overlays were *learned but not promoted into the output.*

## Expected vs actual ratio

| | frontToBuildingsRatio |
| --- | ---: |
| Vanilla **earth** envelope (Mine 1–39) | p5 **0.774**, p50 1.053, mean 1.083, p95 1.524 |
| Vanilla **frost** envelope (40–79) | p5 0.048, p50 0.081, p95 0.106 (frost barely uses Front) |
| Vanilla **global** envelope | p5 0.060, p50 0.905, p95 1.515 |
| **custom_08 actual** | **0.024** |

custom_08 (0.024) is ~32× below the earth p5 (0.774) and below even the global p5 (0.060). Its Front layer holds only **5 tiles** — and all 5 are the **torch markers** written directly by the wrapper (`set_tile("Front", …, 48/80)` at build_smart_edge_wrapper_v2.py:308), **none** from templates.

## Root cause: Front available but not promoted

- The fresh library has **23 templates**; **6 carry Front cells** in their `layerStack`:
  `wall_top` (3 Front cells), `wall_body` (3), `lower_left_outer_corner` (3), `lower_right_outer_corner` (3), `upper_left_inner_corner` (3), `upper_right_inner_corner` (2).
- custom_08 **placed 326 templates**, including front-bearing roles: `wall_body` ×30, `upper_left_inner_corner` ×15, `upper_right_inner_corner` ×17, `lower_left_outer_corner` ×14, `lower_right_outer_corner` ×16. **But 0 of 326 placements wrote a single Front cell.**
- Reason: `EdgeWrapper.template(role, preferred_size)` returns `items[0]` (build_smart_edge_wrapper_v2.py:98) — the **first** template registered for a role. For each role the **Front-less variant is first**, so the Front-bearing variants are never selected. The wrapper's stamp loop *would* write Front (line 193 only skips AlwaysFront/Paths), but it is fed Front-less templates.
- `wall_top` (a fully Front-bearing template) was **never placed at all** (0 placements) — its role isn't emitted by the current boundary classifier, so its shadow overlay never appears.

Not a staleness issue: wrapper (14:24), library + custom_08 (14:31:50–52) were generated together.

## What is missing, by area

- **Shadow strips below walls:** `lower_face_3_tile_stack` ×63 and `floor_to_wall_transition` ×63 were placed but wrote **0 Front** — the wall→floor shadow strip is absent everywhere.
- **Wall-top overlays:** `wall_top` never placed (0×) → no top silhouette overlay.
- **Lower-face overlays:** lower-face templates carry no Front variant and none was selected.
- **Edge overlays:** `left_wall_edge` ×16, `right_wall_edge` ×22 — no Front-bearing edge variants exist in the library yet.
- **Corner overlays:** inner/outer corner templates *do* have Front variants but the Front-less variant was selected.
- **Ladder/shaft opening overlays:** `ladder_opening` ×1 placed; no Front opening-overlay family exists yet.

## Which family caused fallback

The 98→ (custom_08 reports 98; the placement debug shows 4 `ambiguous` + structural fallbacks) marker fallbacks are **Buildings-structural**, triggered by `template(role)` returning none/invalid for a boundary class (e.g. `ambiguous` boundaries with `"no fresh approved boundary template"`). They are **not** Front-related; the Front gap is the selection bug above, not a fallback.

## Conclusion → fix priority

1. **Cheapest, highest-leverage (uses already-learned data):** make `template()` prefer the **Front-bearing variant** of a role when one exists, and ensure `wall_top` (+ paired Front overlay) is actually emitted. This alone should lift the ratio substantially with zero new mining.
2. **Then mine the still-missing Front families** (edge overlays, ladder/shaft opening overlays, dedicated shadow-under-face strips) from vanilla + Moonvillage dungeon maps to reach the earth range.
3. Re-validate with the theme-aware conformance gate (earth target ≈ p5 0.774).

This audit satisfies acceptance item #1. The remaining tasks (mine families, promote templates, atlas, update wrapper, generate custom_09, validators, reports) build on this finding.
