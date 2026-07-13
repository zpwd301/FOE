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


def fragment_reward(
    reward_id: str,
    name: str,
    amount: float,
    required: float,
) -> dict:
    return {
        "type": "consumable",
        "subType": "fragment",
        "amount": amount,
        "requiredAmount": required,
        "assembledReward": {
            "type": "consumable",
            "id": reward_id,
            "name": name,
        },
    }


def entity_with_options(options: list[dict]) -> dict:
    return {
        "components": {
            "AllAge": {
                "production": {"options": options},
            },
        },
    }


class KitProductionTests(unittest.TestCase):
    def test_registry_covers_the_seven_supported_families(self) -> None:
        self.assertEqual(
            set(model.KIT_FAMILY_DEFINITIONS),
            {"oneUp", "renovation", "specialFinish", "supplyFinish", "goodsFinish", "massAid", "store"},
        )
        self.assertEqual(len(model.KIT_ATTR_TO_FAMILY), 7)
        self.assertEqual(model.KIT_FAMILY_DEFINITIONS["specialFinish"]["strength"], "FSP")
        self.assertEqual(model.KIT_FAMILY_DEFINITIONS["store"]["strength"], "Store Building")

    def test_fragment_probability_and_recipe_size_are_applied(self) -> None:
        entity = entity_with_options(
            [
                {
                    "time": 86400,
                    "products": [
                        {
                            "possibleRewards": [
                                {
                                    "chance": 25,
                                    "reward": fragment_reward("one_up_kit", "One Up Kit", 6, 30),
                                },
                            ],
                        },
                    ],
                },
            ]
        )

        production = model.extract_kit_production(entity, "VirtualFuture")

        one_up = production["oneUp"]
        self.assertTrue(math.isclose(one_up["expectedFragmentsPerDay"], 1.5))
        self.assertTrue(math.isclose(one_up["kitEquivalentsPerDay"], 0.05))
        self.assertTrue(math.isclose(one_up["items"][0]["chance"], 0.25))

    def test_direct_kits_are_converted_to_fragment_equivalents(self) -> None:
        entity = entity_with_options(
            [
                {
                    "time": 43200,
                    "product": {
                        "type": "consumable",
                        "subType": "store_building",
                        "id": "store_building",
                        "name": "Store Building",
                        "amount": 1,
                    },
                },
            ]
        )

        production = model.extract_kit_production(entity, "VirtualFuture")

        store = production["store"]
        self.assertTrue(math.isclose(store["kitEquivalentsPerDay"], 2.0))
        self.assertTrue(math.isclose(store["expectedFragmentsPerDay"], 30.0))
        self.assertEqual(store["items"][0]["source"], "kit")

    def test_supply_rushes_are_weighted_by_duration(self) -> None:
        entity = entity_with_options(
            [
                {
                    "time": 86400,
                    "reward": fragment_reward(
                        "rush_mass_supplies_6h",
                        "6h Mass Supply Rush",
                        15,
                        15,
                    ),
                },
            ]
        )

        production = model.extract_kit_production(entity, "VirtualFuture")

        supply = production["supplyFinish"]
        self.assertTrue(math.isclose(supply["kitEquivalentsPerDay"], 1.0))
        self.assertTrue(math.isclose(supply["valuePerDay"], 6.0))
        self.assertEqual(supply["items"][0]["durationHours"], 6.0)

    def test_best_daily_option_is_selected_for_each_family(self) -> None:
        entity = entity_with_options(
            [
                {
                    "time": 86400,
                    "reward": fragment_reward("renovation_kit", "Renovation Kit", 3, 30),
                },
                {
                    "time": 86400,
                    "reward": fragment_reward("renovation_kit", "Renovation Kit", 9, 30),
                },
            ]
        )

        production = model.extract_kit_production(entity, "VirtualFuture")

        self.assertTrue(math.isclose(production["renovation"]["expectedFragmentsPerDay"], 9.0))
        self.assertTrue(math.isclose(production["renovation"]["valuePerDay"], 0.3))

    def test_kit_attributes_do_not_change_existing_default_profiles(self) -> None:
        for attr_key in model.KIT_ATTR_TO_FAMILY:
            self.assertEqual(model.default_weight_for_attr(attr_key), 0.0)
            self.assertEqual(model.overall_raw_weight_for_attr(attr_key), 0.0)
            self.assertEqual(model.fighting_weight_for_attr(attr_key), 0.0)
            self.assertEqual(model.fp_goods_weight_for_attr(attr_key), 0.0)
            self.assertEqual(model.qi_weight_for_attr(attr_key), 0.0)

    def test_export_index_deduplicates_age_invariant_details(self) -> None:
        production = {"oneUp": {"valuePerDay": 0.1, "items": []}}
        records = {
            "BronzeAge": [
                {"entity_id": "building", "kit_production": production},
                {"entity_id": "no-kits", "kit_production": {}},
            ],
            "IronAge": [
                {"entity_id": "building", "kit_production": production},
                {"entity_id": "no-kits", "kit_production": {}},
            ],
            "StoneAge": [
                {"entity_id": "building", "kit_production": {}},
                {"entity_id": "no-kits", "kit_production": {}},
            ],
        }

        index = export_data.kit_production_index(records)

        self.assertNotIn("no-kits", index)
        self.assertEqual(index["building"]["default"], production)
        self.assertEqual(index["building"]["overrides"], {"StoneAge": {}})


if __name__ == "__main__":
    unittest.main()
