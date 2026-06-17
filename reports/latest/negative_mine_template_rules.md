# Negative Mine Template Rules

- `no_loose_structural_tiles` (block): Walls, corners, shadows, ladders, shafts, and openings must be placed as complete approved templates, not single tile IDs.
- `front_shadow_requires_wall_context` (block): Front-layer shadow/overlay tiles require the paired Back/Buildings context from their source template.
- `void_ids_are_not_wall_art` (block): Deep void/filler IDs are not valid structural wall/corner overlays.
- `wall_piece_never_alone` (block): A wall-looking Buildings tile is invalid unless its neighboring template context is present.
- `opening_requires_socket` (block): Ladder/shaft tiles require a source-proven socket template.
- `unapproved_canon_not_generator_ready` (block): Joel_review_needed templates may be used in exact clone tests but not in procedural generation as generator_ready.
