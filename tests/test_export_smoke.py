from pathlib import Path
import json
import py_compile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExportSmokeTests(unittest.TestCase):
    def test_key_json_files_parse(self):
        for rel in [
            "pattern_learning/mine_dungeon_visual_canon_v1/mine_dungeon_visual_canon_v1.json",
            "pattern_learning/mine_dungeon_visual_canon_v1/source_crops.json",
            "pattern_learning/mine_dungeon_visual_canon_v1/negative_mine_template_rules.json",
            "pattern_learning/map_building_blocks/cleaned_blocks/joel_approved_building_blocks_v1.locked.json",
        ]:
            path = ROOT / rel
            if path.exists():
                json.loads(path.read_text(encoding="utf-8"))

    def test_exported_python_compiles(self):
        for path in ROOT.glob("*.py"):
            py_compile.compile(str(path), doraise=True)


if __name__ == "__main__":
    unittest.main()
