# Mine Visual Canon v1 Review Pack Instructions

- Review pack: `pattern_learning/mine_dungeon_visual_canon_v1/joel_review_pack/mine_visual_canon_v1_review_pack.json`
- Decision template: `pattern_learning/mine_dungeon_visual_canon_v1/joel_review_pack/mine_visual_canon_v1_decisions.template.json`
- Atlas: `pattern_learning/mine_dungeon_visual_canon_v1/previews/mine_dungeon_visual_canon_v1_atlas.png`

Workflow:
1. Open the atlas and compare each candidate to its source crop preview.
2. For approved items, copy the decision template to `mine_visual_canon_v1_decisions.json` and set `decision` to `approve`, `visualStatus` to `Joel_approved`, `generatorStatus` to `generator_ready`, and `locked` to `true`.
3. Leave uncertain templates as `unsure`; rejected templates should use `reject`.
4. Run `python import_mine_visual_canon_decisions.py` only after the real decisions file exists.

Starter candidates included: 11
