# Map Building Blocks — Cleaned Next Steps (mines)

## 1. Manual review (Joel) — now unblocked
Review the 8 enlarged contact sheets in
`pattern_learning/map_building_blocks/cleaned_blocks/review_contact_sheets/` and mark the 4
approval packs in `…/cleaned_blocks/review_packs/`. Order and criteria are in
`reports/map_building_blocks_cleaned_review_instructions.md`. You're reviewing **776 filtered
candidates via contact sheets**, not 931 raw entries.

## 2. Promotion step (after approvals) — not yet built
A `promote_cleaned_blocks.py` will read the approval packs, flip each `decision: true` block to
`generatorStatus: generator_ready` + `locked: true` + `visualStatus: approved`, leave all else
`review_needed`, and re-run the validators. This is the **only** path to `generator_ready`.
I'll build it once you've marked at least one pack (or given a rule).

## 3. Recover near-miss floors (optional)
51 blocks were quarantined as "floor clips wall cells" — near-pure 5×5 floors that catch one
wall corner. These are recoverable as `mine_floor_variation` or as edge/transition blocks in a
follow-up reclassification pass, if you want them.

## 4. Variable-rectangle re-cut (optional)
19 cropped blocks couldn't be resolved at 5×5/7×7. A variable-rectangle re-cut (grow to the full
wall/corner extent via anchor detection) would recover most of them. Deferred unless needed.

## 5. Second corpus — Moonvillage Dungeon (.tmx)
Once the mine library is approved, extend the same score→re-cut→clean→review pipeline to the
Moonvillage Dungeon maps. They use **different tilesheets**, so:
- build a separate tile-role model per dungeon tilesheet,
- only surface blocks whose tilesheet is compatible with the generator's `mine.png` (or carry a
  per-tilesheet generator target),
- keep the same "no loose tiles, no auto-promotion" guarantees.

## 6. Generator integration (later)
When a set of mine blocks is approved + locked, wire them into the generator as whole-block
stamps (never loose tiles), gated by the existing wall-grammar conformance validator and the
out-of-bounds failsafe.
