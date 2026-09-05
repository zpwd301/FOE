from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "script"
sys.path.insert(0, str(SCRIPT_DIR))

import building_ranking_model as model  # noqa: E402


def entity_with_reward(reward: dict) -> dict:
    return {
        "components": {
            "AllAge": {
                "production": {
                    "options": [
                        {
                            "time": 86400,
                            "product": {
                                "type": "genericReward",
                                "reward": reward,
                            },
                        },
                    ],
                },
            },
        },
    }


class BlueprintProductionClassificationTests(unittest.TestCase):
    def test_current_or_higher_chest_is_classified_without_changing_total(self) -> None:
        entity = entity_with_reward(
            {
                "type": "chest",
                "id": "genb_higher_age_blueprints_chest_VirtualFuture6",
                "possible_rewards": [
                    {
                        "drop_chance": 40,
                        "reward": {
                            "type": "blueprint",
                            "subType": "X_VirtualFuture_Landmark1",
                            "amount": 6,
                        },
                    },
                    {
                        "drop_chance": 60,
                        "reward": {
                            "type": "blueprint",
                            "subType": "X_SpaceAgeMars_Landmark1",
                            "amount": 6,
                        },
                    },
                ],
            }
        )

        attrs = model.extract_attributes(entity, "VirtualFuture", None)

        self.assertTrue(math.isclose(attrs[model.PROD_BLUEPRINT_ATTR], 6.0))
        self.assertTrue(math.isclose(attrs[model.PROD_BLUEPRINT_CURRENT_OR_HIGHER_ATTR], 6.0))
        self.assertNotIn(model.PROD_BLUEPRINT_RANDOM_ATTR, attrs)

    def test_random_blueprint_is_classified_without_changing_total(self) -> None:
        entity = entity_with_reward(
            {
                "type": "blueprint",
                "subType": "random",
                "id": "blueprint#copper#random#4",
                "amount": 4,
            }
        )

        attrs = model.extract_attributes(entity, "VirtualFuture", None)

        self.assertTrue(math.isclose(attrs[model.PROD_BLUEPRINT_ATTR], 4.0))
        self.assertTrue(math.isclose(attrs[model.PROD_BLUEPRINT_RANDOM_ATTR], 4.0))
        self.assertNotIn(model.PROD_BLUEPRINT_CURRENT_OR_HIGHER_ATTR, attrs)

    def test_blueprint_classification_attributes_do_not_affect_rankings(self) -> None:
        self.assertEqual(model.default_weight_for_attr(model.PROD_BLUEPRINT_CURRENT_OR_HIGHER_ATTR), 0.0)
        self.assertEqual(model.default_weight_for_attr(model.PROD_BLUEPRINT_RANDOM_ATTR), 0.0)


class MotivatedProductionTests(unittest.TestCase):
    def test_motivation_only_resources_are_included_in_daily_production(self) -> None:
        entity = {
            "components": {
                "AllAge": {
                    "production": {
                        "options": [
                            {
                                "time": 43200,
                                "products": [
                                    {
                                        "type": "resources",
                                        "onlyWhenMotivated": True,
                                        "playerResources": {
                                            "resources": {
                                                "strategy_points": 10,
                                                "medals": 20,
                                                "all_goods_of_age": 30,
                                                "special_goods_up_to_age": 4,
                                            },
                                        },
                                        "guildResources": {
                                            "resources": {"iron": 5},
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                },
            },
        }

        attrs = model.extract_attributes(entity, "VirtualFuture", None)

        self.assertEqual(attrs[model.PROD_FP_ATTR], 20)
        self.assertEqual(attrs[model.PROD_MEDALS_ATTR], 40)
        self.assertEqual(attrs[model.PROD_GOODS_ATTR], 68)
        self.assertEqual(attrs["prod_resource_special_goods_up_to_age"], 8)
        self.assertEqual(attrs[model.PROD_GUILD_GOODS_ATTR], 10)


class SpecialGoodsProductionTests(unittest.TestCase):
    def test_each_special_good_is_multiplied_by_unlocked_special_good_eras(self) -> None:
        entity = {
            "components": {
                "AllAge": {
                    "production": {
                        "options": [
                            {
                                "time": 86400,
                                "product": {
                                    "resources": {"each_special_goods_up_to_age": 90},
                                },
                            },
                        ],
                    },
                },
            },
        }

        expected_by_age = {
            "FutureEra": 0,
            "ArcticFuture": 90,
            "VirtualFuture": 180,
            "SpaceAgeAsteroidBelt": 360,
            "SpaceAgeSpaceHub": 720,
            "StellarAgeDiscovery": 720,
        }
        for age, expected in expected_by_age.items():
            with self.subTest(age=age):
                attrs = model.extract_attributes(entity, age, None)
                self.assertEqual(attrs["prod_resource_special_goods_up_to_age"], expected)
                self.assertEqual(attrs[model.PROD_GOODS_ATTR], expected)

    def test_random_special_good_remains_one_reward(self) -> None:
        entity = {
            "components": {
                "AllAge": {
                    "production": {
                        "options": [
                            {
                                "time": 86400,
                                "product": {
                                    "resources": {"random_special_good_up_to_age": 90},
                                },
                            },
                        ],
                    },
                },
            },
        }

        attrs = model.extract_attributes(entity, "SpaceAgeAsteroidBelt", None)

        self.assertEqual(attrs["prod_resource_special_goods_up_to_age"], 90)
        self.assertEqual(attrs[model.PROD_GOODS_ATTR], 90)

    def test_each_special_good_reward_uses_the_same_age_multiplier(self) -> None:
        entity = entity_with_reward(
            {
                "type": "resource",
                "subType": "each_special_goods_up_to_age",
                "amount": 90,
            }
        )

        attrs = model.extract_attributes(entity, "SpaceAgeAsteroidBelt", None)

        self.assertEqual(attrs["prod_resource_special_goods_up_to_age"], 360)
        self.assertEqual(attrs[model.PROD_GOODS_ATTR], 360)


if __name__ == "__main__":
    unittest.main()
