import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "fetch_gb_benefits.py"
SPEC = importlib.util.spec_from_file_location("fetch_gb_benefits", MODULE_PATH)
FETCH_GB_BENEFITS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(FETCH_GB_BENEFITS)


class GreatBuildingBenefitTests(unittest.TestCase):
    def test_parser_reads_image_and_text_benefit_rows_in_order(self):
        segment = """
        <tr id='1'><td>1</td><td>70</td><td><ul>
          <li><img title='military_boost' />&nbsp;(3)</li>
          <li>strategy_points&nbsp;(1)</li>
        </ul></td><!-- START GB REWARD TABLE -->
        """
        self.assertEqual(
            FETCH_GB_BENEFITS.parse_benefit_items(segment),
            [("military_boost", 3), ("strategy_points", 1)],
        )

    def test_checked_in_source_covers_every_building_through_301(self):
        dataset = json.loads((ROOT / "data" / "gb-analysis.json").read_text())
        source = json.loads((ROOT / "data" / "gb-benefits-source.json").read_text())
        self.assertEqual(source["throughTargetLevel"], 301)
        self.assertEqual(source["missingBuildingIds"], [])
        self.assertEqual(set(source["buildings"]), {item["id"] for item in dataset["buildings"]})
        for building_id, building in source["buildings"].items():
            self.assertTrue(building["benefits"], building_id)
            for benefit in building["benefits"]:
                self.assertEqual(len(benefit["values"]), 301, building_id)
                self.assertTrue(
                    all(
                        left <= right
                        for left, right in zip(
                            benefit["values"], benefit["values"][1:]
                        )
                    ),
                    f"{building_id}: {benefit['key']}",
                )

        tower = source["buildings"]["X_BronzeAge_Landmark1"]
        tower_values = {benefit["key"]: benefit["values"] for benefit in tower["benefits"]}
        self.assertEqual(tower_values["random_goods_after_modern"][79], 2 * tower_values["random_goods"][79])

        siphon = source["buildings"]["X_StellarAgeDiscovery_Landmark1"]
        values = {benefit["key"]: benefit["values"] for benefit in siphon["benefits"]}
        self.assertEqual(values["advanced_tactics"][79], 400)
        self.assertEqual(values["advanced_tactics"][300], 1505)
        self.assertEqual(values["supplies"][79], 6_538_811)
        self.assertEqual(values["supplies"][300], 34_264_500)


if __name__ == "__main__":
    unittest.main()
