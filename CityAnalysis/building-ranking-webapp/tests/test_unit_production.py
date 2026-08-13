from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "script"
EXPORT_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(EXPORT_SCRIPT_DIR))

import building_ranking_model as model  # noqa: E402
import export_data  # noqa: E402


def unit_reward(reward_id: str, unit_id: str, name: str, amount: float) -> dict:
    return {
        "type": "unit",
        "subType": unit_id,
        "amount": amount,
        "id": reward_id,
        "name": f"{amount:g}x {name}",
        "unit": {"unitTypeId": unit_id},
    }


def random_unit_product(reward_id: str, chance: float) -> dict:
    return {
        "product": {
            "type": "genericReward",
            "reward": {"id": reward_id},
        },
        "dropChance": chance,
    }


class UnitProductionTests(unittest.TestCase):
    def momiji_style_entity(self) -> dict:
        rewards = {
            "era_unit#short_ranged#CurrentEra#25": unit_reward(
                "era_unit#short_ranged#CurrentEra#25",
                "nail_storm",
                "Nail Storm",
                25,
            ),
            "era_unit#short_ranged#NextEra#29": unit_reward(
                "era_unit#short_ranged#NextEra#29",
                "ghost_blaster",
                "Ghost Blaster",
                29,
            ),
            "unit#rogue#40": unit_reward("unit#rogue#40", "rogue", "Rogue", 40),
        }
        return {
            "components": {
                "AllAge": {
                    "production": {
                        "options": [
                            {
                                "time": 86400,
                                "products": [
                                    {
                                        "type": "random",
                                        "products": [
                                            random_unit_product(
                                                "era_unit#short_ranged#CurrentEra#25",
                                                0.4,
                                            ),
                                            random_unit_product("unit#rogue#40", 0.25),
                                            random_unit_product(
                                                "era_unit#short_ranged#NextEra#29",
                                                0.35,
                                            ),
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    "lookup": {"rewards": rewards},
                },
            },
        }

    def test_extracts_age_class_name_probability_and_expected_output(self) -> None:
        production = model.extract_unit_production(self.momiji_style_entity(), "VirtualFuture")

        self.assertEqual([item["age"] for item in production], ["current", "next", "rogue"])
        current, next_age, rogue = production
        self.assertEqual((current["classKey"], current["classLabel"]), ("ranged", "Ranged"))
        self.assertEqual(current["unitName"], "Nail Storm")
        self.assertTrue(math.isclose(current["expectedPerDay"], 10.0))
        self.assertTrue(math.isclose(current["possiblePerDay"], 25.0))
        self.assertTrue(math.isclose(current["chance"], 0.4))
        self.assertEqual(next_age["unitName"], "Ghost Blaster")
        self.assertTrue(math.isclose(next_age["expectedPerDay"], 10.15))
        self.assertTrue(math.isclose(next_age["chance"], 0.35))
        self.assertEqual((rogue["classKey"], rogue["classLabel"]), ("rogue", "Rogue"))

    def test_details_match_the_aggregated_ranking_attributes(self) -> None:
        entity = self.momiji_style_entity()
        production = model.extract_unit_production(entity, "VirtualFuture")
        attrs = model.extract_attributes(entity, "VirtualFuture", None)

        for attribute_key in model.UNIT_AGE_DEFINITIONS:
            expected = sum(
                item["expectedPerDay"]
                for item in production
                if item["attributeKey"] == attribute_key
            )
            self.assertTrue(math.isclose(expected, attrs[attribute_key]))

    def test_friendly_labels_cover_all_five_standard_unit_classes(self) -> None:
        expected = {
            "light_melee": ("light", "Light"),
            "heavy_melee": ("heavy", "Heavy"),
            "fast": ("fast", "Fast"),
            "short_ranged": ("ranged", "Ranged"),
            "long_ranged": ("artillery", "Artillery"),
        }

        for raw_class, friendly in expected.items():
            with self.subTest(raw_class=raw_class):
                reward = {"type": "unit", "id": f"era_unit#{raw_class}#NextEra#5"}
                self.assertEqual(model.unit_class_details(reward), friendly)

    def test_best_option_is_selected_for_each_age_bucket(self) -> None:
        entity = {
            "components": {
                "AllAge": {
                    "production": {
                        "options": [
                            {
                                "time": 86400,
                                "reward": unit_reward(
                                    "era_unit#heavy_melee#NextEra#4",
                                    "heavy_unit",
                                    "Heavy Unit",
                                    4,
                                ),
                            },
                            {
                                "time": 86400,
                                "reward": unit_reward(
                                    "era_unit#fast#NextEra#6",
                                    "fast_unit",
                                    "Fast Unit",
                                    6,
                                ),
                            },
                        ],
                    },
                },
            },
        }

        production = model.extract_unit_production(entity, "VirtualFuture")

        self.assertEqual(len(production), 1)
        self.assertEqual(production[0]["classLabel"], "Fast")
        self.assertEqual(production[0]["expectedPerDay"], 6.0)

    def test_export_index_deduplicates_age_invariant_details(self) -> None:
        production = [{"attributeKey": "prod_unit_next_age", "unitName": "Archer"}]
        records = {
            "BronzeAge": [{"entity_id": "building", "unit_production": production}],
            "IronAge": [{"entity_id": "building", "unit_production": production}],
            "StoneAge": [{"entity_id": "building", "unit_production": []}],
        }

        index = export_data.unit_production_index(records)

        self.assertEqual(index["building"]["default"], production)
        self.assertEqual(index["building"]["overrides"], {"StoneAge": []})


if __name__ == "__main__":
    unittest.main()
