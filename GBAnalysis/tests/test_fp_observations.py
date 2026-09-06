import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "import_foe_helper_fp_observations.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("fp_observations", MODULE_PATH)
FP_OBSERVATIONS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(FP_OBSERVATIONS)


class FpObservationImporterTests(unittest.TestCase):
    def test_checked_in_observations_cover_expected_rows(self):
        payload = json.loads(
            (ROOT / "data" / "contributor-fp-observations.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["retrievedOn"], "2026-09-06")
        self.assertEqual(
            sum(len(levels) for levels in payload["fpP1ByEra"].values()),
            1965,
        )
        self.assertEqual(payload["fpP1ByEra"]["16"]["233"], 5410)
        self.assertEqual(payload["fpP1ByEra"]["24"]["204"], 6080)

    def test_collect_candidates_validates_recursive_position_rewards(self):
        source = {"exactThroughTargetLevel": 201}
        dataset = {"rewardP1ByEra": {"16": [5] * 201}}
        payload = {
            "status": 200,
            "response": [
                {
                    "id": "X_OceanicFuture_Landmark2",
                    "era": "OceanicFuture",
                    "level": 202,
                    "patron_bonus": [
                        {"rank": 1, "forgepoints": 4605},
                        {"rank": 2, "forgepoints": 2305},
                        {"rank": 3, "forgepoints": 770},
                        {"rank": 4, "forgepoints": 195},
                        {"rank": 5, "forgepoints": 40},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "response.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            candidates, rejected = FP_OBSERVATIONS.collect_candidates(
                [path],
                source,
                dataset,
                {"X_OceanicFuture_Landmark2": 16},
            )
        self.assertEqual(rejected, 0)
        self.assertEqual(candidates["16"][202], [4605])


if __name__ == "__main__":
    unittest.main()
