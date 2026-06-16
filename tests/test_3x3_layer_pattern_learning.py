from __future__ import annotations

import importlib.util
import sys
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location("learn_layer_patterns", ROOT / "learn_layer_patterns.py")
learn = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(learn)


class ThreeByThreeLayerPatternLearningTests(unittest.TestCase):
    def make_records(self):
        return {
            "Back": {
                "width": 3,
                "height": 3,
                "tiles": {(1, 1): ("mine", 5), (1, 2): ("mine", 6)},
                "tileProperties": {(1, 1): {"Water": True}},
            },
            "Buildings": {
                "width": 3,
                "height": 3,
                "tiles": {(1, 0): ("mine", 20)},
                "tileProperties": {},
            },
            "Front": {
                "width": 3,
                "height": 3,
                "tiles": {(1, 1): ("mine", 30)},
                "tileProperties": {},
            },
            "AlwaysFront": {"width": 3, "height": 3, "tiles": {}, "tileProperties": {}},
            "Paths": {"width": 3, "height": 3, "tiles": {}, "tileProperties": {}},
        }

    def test_3x3_observation_preserves_empty_cells(self):
        obs = learn.make_3x3_observation(self.make_records(), 1, 1, ["Back", "Buildings"], {}, {})

        self.assertEqual(obs["cells"]["C"]["Back"]["tile"], "mine:5")
        self.assertEqual(obs["cells"]["C"]["Buildings"]["state"], "empty")
        self.assertIn("C:Buildings", obs["emptyCells"])
        self.assertEqual(obs["cells"]["N"]["Buildings"]["tile"], "mine:20")

    def test_3x3_observation_merges_vanilla_and_placement_properties(self):
        vanilla_index = {"sheets": {"mine": {"5": {"props": {"Type": ["Stone"]}}}}}
        obs = learn.make_3x3_observation(self.make_records(), 1, 1, ["Back"], vanilla_index, {})

        props = set(obs["cells"]["C"]["Back"]["properties"])
        self.assertIn("Water=True", props)
        self.assertIn("Type=Stone", props)
        self.assertGreater(obs["propertyRequirements"]["C:Back:Water=True"], 0)

    def test_structural_layers_are_separate_from_decoration_layers(self):
        structural = learn.make_3x3_observation(self.make_records(), 1, 1, learn.STRUCTURAL_LAYERS, {}, {})
        decoration = learn.make_3x3_observation(
            self.make_records(),
            1,
            1,
            ["Back", "Buildings", "Front", "AlwaysFront", "Paths"],
            {},
            {},
        )

        self.assertEqual(structural["signature"]["layers"], ["Back", "Buildings"])
        self.assertNotIn("Front", structural["signature"]["cells"]["C"])
        self.assertIn("Front", decoration["signature"]["cells"]["C"])

    def test_record_3x3_counts_empty_constraints(self):
        stats = {
            "structural": {
                "patternCounts": learn.Counter(),
                "centerStackCounts": learn.Counter(),
                "categoryCounts": learn.Counter(),
                "patterns": {},
                "examples": defaultdict(list),
                "emptyCellConstraints": learn.Counter(),
                "propertyRequirements": learn.Counter(),
            }
        }
        obs = learn.make_3x3_observation(self.make_records(), 1, 1, ["Back", "Buildings"], {}, {})

        learn.record_3x3_observation(stats, "structural", obs, "Test.tbin", "mine", 1, 1)

        self.assertEqual(stats["structural"]["patternCounts"][obs["patternId"]], 1)
        self.assertEqual(stats["structural"]["emptyCellConstraints"][f"{obs['patternId']}:C:Buildings"], 1)


if __name__ == "__main__":
    unittest.main()
