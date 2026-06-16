# Next Pattern Learning Steps

- Generated: 2026-06-16T08:20:32+00:00

## Learn Next

- Extract edge/corner matrices from high-confidence vanilla structures.
- Separate interior wall grammar from exterior building grammar.
- Learn water-edge transition orientation from vanilla maps with Water=T metadata.
- Learn canopy overlays as non-collision profiles, keeping tile 946 quarantined from blockers.

## Human Review Targets

- wallBodyTiles
- wallTopTiles
- cornerMatrices
- edgeMatrices
- transitionTiles
- canopyOverlayTiles
- shadowTiles
- pathTransitionTiles
- waterEdgeTiles

## Generator Use

- Feed `generator_layer_rules_from_vanilla.json` into the marker generator first.
- Extend validators to reject illegal stacks before TMX/TMJ output is allowed.
- Keep production output disabled until stylepack structural roles resolve to approved profiles.
