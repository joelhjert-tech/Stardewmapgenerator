# Joel-Approved Building Blocks — Validation Results

All validators run after importing Joel's `_approvedbyjoel` sheets and promoting into the
derived locked library.

| Validator | Result |
|---|---|
| `validate_joel_building_block_approvals.py` | **174/174 valid** (core 144, decoration 29, review_needed 1) |
| `validate_cleaned_map_building_blocks.py` | **PASS** (0 errors) — now tolerates `_approvedbyjoel`-renamed sheets |
| `validate_map_building_blocks.py` | **PASS** (0 errors) |
| `validate_final_building_block_approval_packs.py` | **absent** — not created in any prior pass; skipped |
| `validate_stylepacks.py` | **PASS** (0 errors, 4 pre-existing warnings) |
| `validate_approved_tags.py` | **PASS** (0 errors, 0 warnings) |
| `run_validation_tests.py` | **OK** (88 tests) |

## Per-block approval validation
Every promoted block passed all of: exists in cleaned library, appears in the approved-sheet
mapping, not quarantined, has a preview, has source map + coordinate, complete multi-layer
cell data, has a block type, has all quality scores, is not a loose single tile, obeys the
negative building-block rules (void-not-art, front-requires-base, not-a-singleton), and —
for core lane — carries no object/decoration/crop/void contamination. Openings are barred
from `generator_ready`.

No block was promoted on filename alone: the sheet→block mapping is derived from the exact
deterministic selection that rendered the sheets (`sheet_selections`), **not OCR**.
