# Mine Visual Canon v1 Independent Validation Results

- Date: 2026-06-16
- Scope: review and approval-prep only
- New custom map generated: no
- Production map generated: no

| Check | Result | Notes |
|---|---|---|
| `python validate_mine_visual_canon.py` | PASS | 18 templates, 0 issues |
| `python validate_mine_visual_canon.py --locked` | PASS | No locked derived canon exists yet; base canon remains review-gated |
| `python validate_source_crop_remakes.py` | PASS | 2 remakes checked, exact layer-stack match |
| `python validate_fresh_mine_dungeon_templates.py` | PASS | 23 templates, 20 families, 6448 clusters |
| `python validate_visual_template_output.py` | PASS | 5 checks |
| `python validate_marker_map.py --layout-profile dungeon` | PASS | Marker fallback path still valid |
| `python validate_layer_grammar.py` | PASS | `markerPass=True`; `structuralProductionReady=False` remains expected |
| `python validate_out_of_bounds.py` | PASS | escapes=0, unreachableExits=0, deadPockets=0 |
| `python validate_stylepacks.py` | PASS | errors=0, warnings=4 |
| `python validate_approved_tags.py` | PASS | 0 errors, 0 warnings |
| `python run_validation_tests.py` | PASS | 88 tests |

Verdict: validation passed for canon review prep. The canon is not generator-approved until Joel decisions are imported into a derived locked canon.
