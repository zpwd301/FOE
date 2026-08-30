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


if __name__ == "__main__":
    unittest.main()
