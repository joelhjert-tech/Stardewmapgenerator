# Mine Visual Canon Decision Importer Design

- Script: `import_mine_visual_canon_decisions.py`
- Input: `pattern_learning/mine_dungeon_visual_canon_v1/joel_review_pack/mine_visual_canon_v1_decisions.json`
- Output: `pattern_learning/mine_dungeon_visual_canon_v1/mine_dungeon_visual_canon_v1.locked.json`
- The original canon JSON is not overwritten.

Rules:
- Only `decision: approve` can become `Joel_approved`.
- Only approved decisions can become `generator_ready`.
- Only approved decisions can be locked.
- Rejected templates become `rejected` + `disabled`.
- Unsure templates remain review-gated as `needs_review` + `marker_fallback_only`.
- No template can be locked without source crop, preview, layer stack, and non-loose structural evidence.
- A full import report is written after import.
