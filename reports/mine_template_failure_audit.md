# Mine Template Failure Audit

The previous visual path still used `MineWallPatternResolver`, which chose individual wall IDs from role lists such as wall tops, bodies, lower faces, side edges, and front shadows.

## Failure Point
- `generate_visual_map_v2.py` called `MineWallPatternResolver().apply(p)` after floor decoration.
- `MineWallPatternResolver` computed a wall shell from semantic floor cells and then selected single tile IDs with deterministic pick lists.
- The template library was recorded in metadata, but the wall construction path did not stamp exact vanilla layer-stack templates.
- Back/Buildings/Front relationships were therefore approximate instead of copied from source vanilla coordinates.
- Ladder openings were built from a hardcoded stack and side pieces, not an extracted complete vanilla opening template.

## Why It Looked Wrong
- Correct-looking IDs were sometimes present, but their neighboring IDs and layers were not vanilla source windows.
- Role lists overrode the intended template grammar.
- The validator checked broad sanity, not template provenance for every wall tile.

## Hard Fix
- Mine/dungeon wall visuals now require `GoldenMineTemplateResolver` and metadata-covered golden template placements.
- Any missing wall/corner/opening/ladder template must fall back to marker-only or fail closed.
