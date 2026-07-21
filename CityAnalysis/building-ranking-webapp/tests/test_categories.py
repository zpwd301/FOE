from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "script"
sys.path.insert(0, str(SCRIPT_DIR))

import building_ranking_model as model  # noqa: E402


class BuildingCategoryTests(unittest.TestCase):
    def test_cop_event_years_share_the_cultural_settlement_category(self) -> None:
        self.assertEqual(
            model.building_category_label("W_MultiAge_COP24A9"),
            model.CULTURAL_SETTLEMENT_REWARDS,
        )
        self.assertEqual(
            model.building_category_label("W_MultiAge_COP25A1"),
            model.CULTURAL_SETTLEMENT_REWARDS,
        )

    def test_similar_event_abbreviations_remain_year_specific(self) -> None:
        self.assertEqual(
            model.building_category_label("W_MultiAge_CUP23A10"),
            "CUP 2023 Event Rewards",
        )

    def test_category_options_merge_and_deduplicate_cop_years(self) -> None:
        records = [
            {"entity_id": "W_MultiAge_COP24A9"},
            {"entity_id": "W_MultiAge_COP25A1"},
            {"entity_id": "W_MultiAge_ANNI26A1"},
        ]

        categories = model.building_category_options(records)

        self.assertEqual(categories.count(model.CULTURAL_SETTLEMENT_REWARDS), 1)
        self.assertNotIn("COP 2024 Event Rewards", categories)
        self.assertNotIn("COP 2025 Event Rewards", categories)
        self.assertLess(
            categories.index(model.CULTURAL_SETTLEMENT_REWARDS),
            categories.index("ANNI 2026 Event Rewards"),
        )


if __name__ == "__main__":
    unittest.main()
