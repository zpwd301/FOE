import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build_dataset.py"
SPEC = importlib.util.spec_from_file_location("build_dataset", MODULE_PATH)
BUILD_DATASET = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(BUILD_DATASET)


class DatasetBuilderTests(unittest.TestCase):
    def test_checked_in_dataset_has_expected_coverage(self):
        dataset_path = Path(__file__).parents[1] / "data" / "gb-analysis.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        self.assertEqual(dataset["maxLevel"], 301)
        self.assertEqual(dataset["schemaVersion"], 3)
        self.assertEqual(len(dataset["buildings"]), 49)
        self.assertEqual(dataset["coverage"]["incompleteRewardEraMaxLevels"], {})
        self.assertEqual(dataset["coverage"]["upgradeCostsThroughLevel"], 301)
        self.assertEqual(dataset["coverage"]["levelUnlockCostsThroughLevel"], 301)
        self.assertEqual(dataset["coverage"]["medalsThroughLevel"], 301)
        self.assertEqual(dataset["coverage"]["blueprintsThroughLevel"], 301)
        self.assertEqual(dataset["coverage"]["contributorRewardsThroughLevel"], 301)
        self.assertEqual(dataset["coverage"]["exactContributorRewardsThroughLevel"], 201)
        self.assertEqual(dataset["coverage"]["estimatedContributorRewardsFromLevel"], 202)
        arc = next(item for item in dataset["buildings"] if item["name"] == "The Arc")
        self.assertEqual(arc["firstTenLevelCosts"][-1], 970)
        self.assertEqual(dataset["rewardP1ByEra"]["14"][79], 1375)
        self.assertEqual(dataset["medalP1ByEra"]["14"][173], 89145)
        self.assertEqual(dataset["blueprintsByLevel"][80], [15, 11, 9, 7, 6])
        siphon = next(
            item
            for item in dataset["buildings"]
            if item["id"] == "X_StellarAgeDiscovery_Landmark1"
        )
        self.assertEqual(siphon["name"], "Shattered Horizon Siphon")
        self.assertEqual((siphon["width"], siphon["length"]), (4, 4))
        self.assertEqual(sum(siphon["foundationGoods"].values()), 26000)
        self.assertEqual(siphon["firstTenLevelCosts"], [
            1240, 1750, 3080, 4630, 6070, 7620, 9380, 11000, 12870, 14530
        ])
        self.assertEqual(dataset["rewardP1ByEra"]["24"][79], 1970)
        self.assertEqual(dataset["rewardP1ByEra"]["24"][200], 5975)
        self.assertEqual(dataset["medalP1ByEra"]["24"][200], 578833)
        self.assertEqual(dataset["rewardP1ByEra"]["24"][300], 9710)
        self.assertEqual(dataset["medalP1ByEra"]["24"][300], 940762)
        self.assertEqual(
            dataset["sources"]["contributorRewards"]["estimation"]["medalP1"][
                "exponent"
            ],
            1.200964,
        )
        self.assertEqual(
            len(dataset["sources"]["contributorRewards"]["directCapturedRewards"]),
            8,
        )
        self.assertEqual(
            dataset["coverage"]["exactMedalTargetLevelRangesByEra"]["16"],
            [[1, 301]],
        )
        self.assertEqual(dataset["blueprintsByLevel"][300], [44, 32, 25, 20, 17])
        self.assertEqual(siphon["levelUnlockFormula"]["goodsPerTypePerStep"], 275)
        self.assertEqual(
            siphon["levelUnlockFormula"]["resourcesPerStep"],
            {"money": 97200, "supplies": 97200, "medals": 97200},
        )
        catalyst = next(
            item for item in dataset["buildings"] if item["name"] == "Cosmic Catalyst"
        )
        self.assertEqual(
            catalyst["levelUnlockFormula"],
            {
                "startLevel": 11,
                "blueprintSets": 1,
                "goodsPerTypePerStep": 150,
                "resourcesPerStep": {"dark_matter": 100},
            },
        )

    def test_extract_reward_tables(self):
        arrays = ",\n".join(f"{era}: [5, 10, 15]" for era in [0, *range(2, 25)])
        source = f"let GreatBuildings = {{ Rewards: {{\n{arrays}\n}}, Other: {{}} }};"
        tables = BUILD_DATASET.extract_reward_tables(source)
        self.assertEqual(tables[0], [5, 10, 15])
        self.assertEqual(tables[24], [5, 10, 15])

    def test_positive_foundation_resources_omits_zero_pseudo_resources(self):
        entity = {
            "requirements": {
                "cost": {"resources": {"money": 0, "population": 0, "wine": 50}}
            }
        }
        self.assertEqual(BUILD_DATASET.positive_foundation_resources(entity), {"wine": 50})

    def test_build_dataset_rejects_non_ten_seed_costs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extension = root / "extension"
            source_path = extension / "js" / "greatbuildings.js"
            source_path.parent.mkdir(parents=True)
            arrays = ",\n".join(f"{era}: [5]" for era in [0, *range(2, 25)])
            source_path.write_text(f"const x = {{ Rewards: {{ {arrays} }} }};", encoding="utf-8")
            (extension / "manifest.json").write_text(json.dumps({"version": "test"}))
            entities_path = root / "entities.json"
            entities_path.write_text(
                json.dumps(
                    {
                        "bad": {
                            "id": "bad",
                            "name": "Bad",
                            "type": "greatbuilding",
                            "requirements": {"min_era": "NoAge", "cost": {"resources": {}}},
                            "strategy_points_for_upgrade": [1],
                        }
                    }
                )
            )
            contributor_path = root / "contributor.json"
            contributor_path.write_text(
                json.dumps(
                    {
                        "throughTargetLevel": 201,
                        "source": "test",
                        "medalP1ByEra": {"0": [1] * 201},
                        "blueprintsByLevel": [[0, 0, 0, 0, 0]] * 201,
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "Expected 10 seed costs"):
                BUILD_DATASET.build_dataset(source_path, entities_path, contributor_path)


if __name__ == "__main__":
    unittest.main()
