import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
REWARD_PATH = ROOT / "data" / "contributor-rewards-source.json"
SCAN_PATH = ROOT.parent / "Sniping" / "output" / "neighbors_scan_2026-04-23.json"


def game_round(value):
    return math.floor(value + 0.500001)


class ContributorRewardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rewards = json.loads(REWARD_PATH.read_text(encoding="utf-8"))
        cls.dataset = json.loads((ROOT / "data" / "gb-analysis.json").read_text(encoding="utf-8"))

    def test_checked_in_tables_preserve_sourced_values_and_extend_through_301(self):
        self.assertEqual(self.rewards["throughTargetLevel"], 301)
        self.assertEqual(self.rewards["exactThroughTargetLevel"], 201)
        self.assertEqual(self.rewards["estimatedFromTargetLevel"], 202)
        self.assertEqual(set(self.rewards["medalP1ByEra"]), {"0", *map(str, range(2, 25))})
        self.assertTrue(all(len(values) == 301 for values in self.rewards["fpP1ByEra"].values()))
        self.assertTrue(all(len(values) == 301 for values in self.rewards["medalP1ByEra"].values()))
        self.assertEqual(len(self.rewards["blueprintsByLevel"]), 301)
        self.assertEqual(self.rewards["blueprintsByLevel"][80], [15, 11, 9, 7, 6])
        self.assertEqual(
            [self.rewards["medalP1ByEra"]["24"][index] for index in (0, 79, 200)],
            [1066, 190715, 578833],
        )
        self.assertEqual(self.rewards["medalMaxTargetLevelByEra"]["24"], 301)
        self.assertEqual(self.rewards["medalExactMaxTargetLevelByEra"]["24"], 201)
        self.assertEqual(self.rewards["medalP1ByEra"]["14"][195], 102874)
        self.assertEqual(self.rewards["fpP1ByEra"]["24"][300], 9710)
        self.assertEqual(self.rewards["medalP1ByEra"]["24"][300], 940850)
        self.assertEqual(self.rewards["blueprintsByLevel"][300], [44, 32, 25, 20, 17])
        self.assertEqual(
            self.rewards["estimation"]["fpP1"]["backtest"]["maximumAbsoluteError"],
            5,
        )
        self.assertEqual(
            self.rewards["estimation"]["blueprints"]["rollingBacktest"][
                "maximumAbsoluteError"
            ],
            1,
        )

    @unittest.skipUnless(SCAN_PATH.is_file(), "local live-game construction capture is unavailable")
    def test_tables_match_all_captured_live_medal_and_blueprint_rewards(self):
        scan = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
        buildings = {building["id"]: building for building in self.dataset["buildings"]}
        checked = 0
        for player in scan["players"]:
            for great_building in player.get("great_buildings") or []:
                summary = (great_building.get("summary") or {}).get("great_building") or {}
                building = buildings.get(summary.get("city_entity_id"))
                current_level = summary.get("level")
                if not building or not isinstance(current_level, int) or current_level >= 201:
                    continue
                target_level = current_level + 1
                medal_p1 = self.rewards["medalP1ByEra"][str(building["eraId"])][target_level - 1]
                expected_medals = [
                    medal_p1,
                    game_round(medal_p1 / 2),
                    game_round(medal_p1 / 4),
                    game_round(medal_p1 / 10),
                    game_round(medal_p1 / 20),
                ]
                expected_blueprints = self.rewards["blueprintsByLevel"][target_level - 1]
                for ranking in (great_building.get("construction") or {}).get("rankings", []):
                    reward = ranking.get("reward")
                    rank = ranking.get("rank")
                    if not reward or not rank:
                        continue
                    self.assertEqual(
                        (reward.get("resources") or {}).get("medals", 0),
                        expected_medals[rank - 1],
                    )
                    self.assertEqual(
                        reward.get("blueprints", 0) or 0,
                        expected_blueprints[rank - 1],
                    )
                    checked += 1
        self.assertEqual(checked, 5670)


if __name__ == "__main__":
    unittest.main()
