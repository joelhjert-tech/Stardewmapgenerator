from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))

from golden_mine_template_resolver import GoldenMineTemplateResolver  # noqa: E402
import validate_golden_mine_template_output as validator  # noqa: E402


def write_tmx(path: Path, width: int, height: int, back: list[int], buildings: list[int], front: list[int] | None = None) -> None:
    front = front or [0] * (width * height)
    zero = [0] * (width * height)

    def csv(vals: list[int]) -> str:
        rows = []
        for y in range(height):
            rows.append(",".join(str(v) for v in vals[y * width:(y + 1) * width]))
        return "\n" + ",\n".join(rows) + "\n"

    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.10.2" orientation="orthogonal" renderorder="right-down" width="{width}" height="{height}" tilewidth="16" tileheight="16" infinite="0">
  <properties>
   <property name="entrance" value="1 1"/>
   <property name="exit" value="1 1"/>
  </properties>
  <tileset firstgid="1" name="mine" tilewidth="16" tileheight="16" tilecount="288" columns="16"><image source="mine.png" width="256" height="288"/></tileset>
  <layer id="1" name="Back" width="{width}" height="{height}"><data encoding="csv">{csv(back)}  </data></layer>
  <layer id="2" name="Buildings" width="{width}" height="{height}"><data encoding="csv">{csv(buildings)}  </data></layer>
  <layer id="3" name="Front" width="{width}" height="{height}"><data encoding="csv">{csv(front)}  </data></layer>
  <layer id="4" name="AlwaysFront" width="{width}" height="{height}"><data encoding="csv">{csv(zero)}  </data></layer>
  <layer id="5" name="Paths" width="{width}" height="{height}"><data encoding="csv">{csv(zero)}  </data></layer>
</map>
""",
        encoding="utf-8",
    )


class GoldenMineTemplateTests(unittest.TestCase):
    def test_missing_wall_template_causes_fallback_required(self):
        with tempfile.TemporaryDirectory() as td:
            resolver = GoldenMineTemplateResolver(Path(td) / "missing.json")
            self.assertFalse(resolver.can_generate_visual_walls())
            self.assertTrue(resolver.missing_required_roles())

    def test_mine_wall_tile_cannot_appear_outside_golden_template(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            back = [139] * 9
            buildings = [0] * 9
            buildings[4] = 70 + 1
            tmx = root / "bad.tmx"
            write_tmx(tmx, 3, 3, back, buildings)
            (root / "metadata.json").write_text(json.dumps({"goldenTemplatePlacements": []}), encoding="utf-8")
            result = validator.validate_map(tmx)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("not covered by a golden template" in e for e in result["errors"]))

    def test_tile_220_back_placement_fails_without_golden_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            back = [139] * 9
            back[4] = 220 + 1
            tmx = root / "bad220.tmx"
            write_tmx(tmx, 3, 3, back, [0] * 9)
            (root / "metadata.json").write_text(json.dumps({"goldenTemplatePlacements": []}), encoding="utf-8")
            result = validator.validate_map(tmx)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("Tile 220 appears on Back" in e for e in result["errors"]))

    def test_tile_186_random_placement_fails_without_template_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            back = [139] * 9
            back[4] = 186 + 1
            tmx = root / "bad186.tmx"
            write_tmx(tmx, 3, 3, back, [0] * 9)
            (root / "metadata.json").write_text(json.dumps({"goldenTemplatePlacements": []}), encoding="utf-8")
            result = validator.validate_map(tmx)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("outside golden under-wall template context" in e for e in result["errors"]))

    def test_custom_03_golden_output_validates_when_present(self):
        tmx = ROOT / "prototype_visual_maps" / "dungeon_review" / "custom_03_golden_template_fixed" / "custom_03_golden_template_fixed.tmx"
        if not tmx.exists():
            self.skipTest("custom_03 golden output has not been generated yet")
        result = validator.validate_map(tmx)
        self.assertEqual(result["status"], "PASS", result["errors"][:5])


if __name__ == "__main__":
    unittest.main()
