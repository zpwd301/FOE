from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "script"
sys.path.insert(0, str(SCRIPT_DIR))

import comprehensive_production_without_percentage_boost_report as report  # noqa: E402


class PopulationImpactTests(unittest.TestCase):
    def test_population_provided_is_summed_across_selected_components_and_count(self) -> None:
        entity = {
            "components": {
                "AllAge": {"staticResources": {"resources": {"population": 100}}},
                "VirtualFuture": {"staticResources": {"resources": {"population": 20}}},
            },
        }

        self.assertEqual(report.total_population_impact(entity, "VirtualFuture", 3), 360)

    def test_population_consumed_remains_negative_and_is_multiplied_by_count(self) -> None:
        entity = {"staticResources": {"resources": {"population": -75}}}

        self.assertEqual(report.total_population_impact(entity, "VirtualFuture", 2), -150)


if __name__ == "__main__":
    unittest.main()
