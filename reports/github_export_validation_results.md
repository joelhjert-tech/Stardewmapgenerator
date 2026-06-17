# GitHub Export Validation Results

- Scope: clean mine/dungeon export repo
- Source assets included: no
- Rendered preview PNGs included: no

| Check | Result | Notes |
|---|---|---|
| JSON parse check | PASS | 52 JSON files parsed |
| Python compile check | PASS | Root Python files compiled via `py_compile` |
| Import smoke check | PASS | Imported core mine/dungeon modules and validators |
| Export smoke unit tests | PASS | 2 tests passed |
| `validate_mine_visual_canon.py` | SKIPPED/EXPECTED FAIL | Requires preview PNGs intentionally excluded from public-safe export |
| `validate_mine_visual_canon.py --locked` | SKIPPED/EXPECTED FAIL | Same preview PNG dependency; no locked canon imported |
| `validate_marker_map.py --layout-profile dungeon` | SKIPPED | Requires `stylepacks/stylepack_schema.json`, excluded from focused export |
| `validate_out_of_bounds.py` | SKIPPED | Default target references generated marker maps not included in export |
| `validate_layer_grammar.py --marker-only` | SKIPPED | Requires broad `learn_layer_patterns.py`, excluded from focused export |

Verdict: export-level checks passed. Asset/support-dependent validators are intentionally not marked PASS in the clean repo.
