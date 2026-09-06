import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from serve_static import (  # noqa: E402
    IMMUTABLE_CACHE,
    NO_STORE_CACHE,
    REVALIDATE_CACHE,
    cache_control_for_path,
    load_user_input,
    save_user_input,
)


class StaticServerCacheTests(unittest.TestCase):
    def test_fingerprinted_resources_are_immutable(self):
        self.assertEqual(
            cache_control_for_path("/assets/app.0123456789ab.js"), IMMUTABLE_CACHE
        )
        self.assertEqual(
            cache_control_for_path("/assets/gb-analysis.abcdef012345.json?v=ignored"),
            IMMUTABLE_CACHE,
        )

    def test_entry_points_and_unversioned_files_revalidate(self):
        self.assertEqual(cache_control_for_path("/"), REVALIDATE_CACHE)
        self.assertEqual(cache_control_for_path("/index.html"), REVALIDATE_CACHE)
        self.assertEqual(cache_control_for_path("/asset-manifest.json"), REVALIDATE_CACHE)

    def test_user_input_api_is_never_cached(self):
        self.assertEqual(cache_control_for_path("/api/user-input"), NO_STORE_CACHE)

    def test_user_input_round_trips_through_a_local_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "dashboard-input.json"
            self.assertEqual(load_user_input(state_file), {})
            expected = {
                "buildingId": "AllAge",
                "rageTargetLevel": 101,
                "rageArcBonuses": [100, 100, 100, 90, 90],
            }
            save_user_input(state_file, expected)
            self.assertEqual(load_user_input(state_file), expected)

            state_file.write_text("not json", encoding="utf-8")
            self.assertEqual(load_user_input(state_file), {})


if __name__ == "__main__":
    unittest.main()
