# Map Building Blocks — Cleaned Review Instructions (mines)

You no longer review 931 raw candidates. The cleaning pass scored every block, re-cut the
cropped ones with larger context, quarantined the noisy/misclassified ones, and rendered
focused enlarged contact sheets of only the strong candidates. Review the **contact sheets**,
then mark **approval packs**.

## Review in this order

Contact sheets live in
`pattern_learning/map_building_blocks/cleaned_blocks/review_contact_sheets/`. Each card shows
the **combined** render (large), the **Back / Buildings / Front** layer splits (small), and
the blockId / type / size / frequency / scores / source / flags.

1. **`review_floor_blocks_large.png`** — floor bases & variations. The safest, highest-volume
   family. Approve clean repeated floor; reject anything that shows a wall edge or object.
2. **`review_wall_edges_large.png`** — left/right side-wall transitions. Approve those showing
   a clean wall column beside a floor column; reject cropped void or stray light/object.
3. **`review_wall_forward_lower_face_large.png`** — lower wall faces with floor below.
4. **`review_wall_body_large.png`** — wall bodies, **re-cut to 5×5/7×7** so the wall→floor/void
   relationship is whole. Approve coherent wall bodies; reject any that still look like a flat
   slab with no face.
5. **`review_corners_large.png`** — inner/outer corners (outer corners re-cut to 5×5/7×7).
   Approve only true corner relationships (two wall arms + floor/void in the opposite quadrant).
6. **`review_shadow_and_front_overlay_large.png`** — blocks carrying Front shadow/overlay paired
   with a wall. Confirm the shadow sits on/above the wall, not floating over floor.
7. **`review_openings_large.png`** — ladder/shaft sockets. The vanilla mine corpus yielded
   essentially **no clean repeated opening blocks** (ladders are unique placements), so this
   sheet is near-empty by design — that is expected, not a bug.
8. **`review_quarantined_examples_large.png`** — a sample of what was **rejected** and why.
   **Do not approve from this sheet.** It exists so you can sanity-check the filter.

## How to mark decisions

Approval packs live in `pattern_learning/map_building_blocks/cleaned_blocks/review_packs/`:
`floor_blocks_approval_pack.json`, `wall_blocks_approval_pack.json`,
`corner_blocks_approval_pack.json`, `opening_blocks_approval_pack.json`.

Each item has `"decision": null`. Set it to:
- `true` — approve (a later promotion step flips it to `generator_ready` + `locked`).
- `false` — reject.
Use `"notes"` for anything you want me to act on. You can also just tell me a rule
(e.g. "approve all floor_base with reuse ≥ 0.95", "reject any wall_body with visible void > 30%").

## What to approve / reject

**Approve** when the combined render reads as a complete, repeatable mine structure and the
layer splits look right (floor on Back, wall on Buildings, shadow on Front). Prefer higher
`reuse` and `freq`.

**Reject** when you see: a structure cut off at the edge, a flat featureless slab, a stray
torch/ladder/object in a wall or floor block, void where floor/wall should be, or a label that
doesn't match the picture.

## Why this matters

`generator_ready` is **never** set automatically. Approval is the only path, and only approved
blocks are promoted. Everything else stays `review_needed`. This keeps unsafe or cropped tiles
out of the generator while still letting the clean majority through quickly.
