# custom_09 Front Promotion Checkpoint — Validation

- Date: 2026-06-16 · All scripts run read-only (except their own report outputs).

| Validator | Result | Notes |
| --- | --- | --- |
| `run_validation_tests.py` | **PASS** (exit 0) | Full regression suite green after the wrapper edits. |
| `validate_fresh_mine_dungeon_templates.py` | **PASS** (exit 0) | Fresh template library still valid (repeated-source evidence intact; no loose single-tile structural placement). |
| `validate_mine_wall_grammar_conformance.py --theme earth` (on custom_09) | **FAIL (flat)** | Only `frontToBuildingsRatio` below earth p5 (0.445 vs 0.774). All other metrics within envelope. Improved from custom_08 (0.024). |
| `validate_stylepacks.py` | **PASS** (0 errors, 4 expected `marker_only_required` warnings) | Unchanged. |
| `validate_approved_tags.py` | **PASS** (0/0) | Approved DB tags unaffected. |
| custom_09 base prototype validation (`validation_report.md`) | **PASS** | tmxParsed, tmjParsed, tilesheetResolved, entranceExitReachable, boundarySealed, tile946Absent. |

## No loose / unsafe placement (proved)

- `noLooseStructuralTiles = True` in metadata; every Front cell was written by a **complete template** (`frontCellsWritten = 169`, all from `wall_top` + the two inner-corner templates).
- `skippedFrontBearing = 0`; void-only Front templates (tile 77) were not stamped.
- Marker fallback still active (`fallbackCount = 36`) for boundary classes with no safe complete template.

## Notes
- `validate_marker_map.py`, `validate_layer_grammar.py`, `validate_out_of_bounds.py` target the marker_tests semantic maps, not this visual prototype, so they were not re-pointed at custom_09; the theme-aware `validate_mine_wall_grammar_conformance.py` is the applicable gate for the visual TMX and was run.
- `validate_custom_09_front_overlay_output.py` does not yet exist (belongs to the later full mining mission); this checkpoint reuses the existing fresh-template + conformance validators.
