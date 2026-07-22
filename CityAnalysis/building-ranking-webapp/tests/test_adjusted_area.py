from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "script"
sys.path.insert(0, str(SCRIPT_DIR))

import building_ranking_model as model  # noqa: E402


ROAD_ATTRS = {"generic_streetconnectionrequirement_requiredlevel": 1}


class AdjustedAreaTests(unittest.TestCase):
    def test_odd_shorter_side_rounds_road_allowance_up(self) -> None:
        record = {"area": 15, "width": 3, "length": 5, "attrs": ROAD_ATTRS}

        self.assertEqual(model.road_area_allowance(record), 2)
        self.assertEqual(model.adjusted_area(record), 17)

    def test_even_shorter_side_needs_no_additional_rounding(self) -> None:
        record = {"area": 20, "size": "4x5", "attrs": ROAD_ATTRS}

        self.assertEqual(model.road_area_allowance(record), 2)
        self.assertEqual(model.adjusted_area(record), 22)

    def test_building_without_road_uses_real_area(self) -> None:
        record = {"area": 15, "width": 3, "length": 5, "attrs": {}}

        self.assertEqual(model.road_area_allowance(record), 0)
        self.assertEqual(model.adjusted_area(record), 15)


if __name__ == "__main__":
    unittest.main()
