# Map Building Blocks — Generator Integration Plan (not yet integrated)

The generator should consume the block library as COMPLETE blocks:
1. Choose a block by `blockType` (e.g. mine_wall_forward_lower_face) and `sizeClass`.
2. Filter to `generatorStatus: generator_ready` + `locked: true` (Joel-approved) only.
3. Check `requiredNeighborContext` / masks (wallMask/floorMask) against the target cells.
4. Place the ENTIRE block's layer stack (Back+Buildings+Front) — never a partial/loose tile.
5. Apply negative rules (`negative_building_block_rules.json`): no loose structural tiles, front-overlay blocks need their paired wall base, corners need matching edges.
6. If no approved block matches the context, fall back to a marker (as Smart Edge-Wrapper v2 already does).
Do not integrate until blocks are reviewed and promoted to generator_ready.
