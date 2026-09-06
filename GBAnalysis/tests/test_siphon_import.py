import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "import_foe_helper_siphon.py"
SPEC = importlib.util.spec_from_file_location("import_foe_helper_siphon", MODULE_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(IMPORTER)


class SiphonImportTests(unittest.TestCase):
    def test_imports_contiguous_p1_data_and_validates_reported_positions(self):
        payload = {
            "status": 200,
            "response": [
                {
                    "id": IMPORTER.BUILDING_ID,
                    "level": 1,
                    "patron_bonus": [
                        {"rank": 1, "forgepoints": 15, "medals": 1066, "blueprints": 0}
                    ],
                },
                {
                    "id": IMPORTER.BUILDING_ID,
                    "level": 2,
                    "patron_bonus": [
                        {"rank": 1, "forgepoints": 20, "medals": 1647, "blueprints": 1},
                        {"rank": 2, "forgepoints": 10, "medals": 824, "blueprints": 0},
                    ],
                },
            ],
        }
        source = {"blueprintsByLevel": [[0, 0, 0, 0, 0], [1, 0, 0, 0, 0]]}
        merged = IMPORTER.merge_siphon_rewards(source, payload, max_level=2)
        self.assertEqual(merged["medalP1ByEra"]["24"], [1066, 1647])
        self.assertEqual(merged["validationFpP1ByEra"]["24"], [15, 20])
        self.assertEqual(merged["medalMaxTargetLevelByEra"]["24"], 2)

    def test_rejects_a_gap_in_target_levels(self):
        payload = {
            "status": 200,
            "response": [
                {
                    "id": IMPORTER.BUILDING_ID,
                    "level": 1,
                    "patron_bonus": [
                        {"rank": 1, "forgepoints": 15, "medals": 1066, "blueprints": 0}
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "missing target levels"):
            IMPORTER.parse_response(payload, max_level=2)


if __name__ == "__main__":
    unittest.main()
