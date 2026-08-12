from __future__ import annotations

import gzip
import json
import re
import sys
import unittest
from pathlib import Path


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT_DIR = WEBAPP_ROOT / "scripts"
sys.path.insert(0, str(EXPORT_SCRIPT_DIR))

import export_data  # noqa: E402


class ExportAssetTests(unittest.TestCase):
    def test_default_age_is_space_age_asteroid_belt(self) -> None:
        data_dir = WEBAPP_ROOT / "data"
        core = json.loads((data_dir / "ranking-core.json").read_text(encoding="utf-8"))

        self.assertEqual(core["metadata"]["defaultAge"], "SpaceAgeAsteroidBelt")

    def test_core_and_every_age_have_matching_json_and_gzip(self) -> None:
        data_dir = WEBAPP_ROOT / "data"
        core = json.loads((data_dir / "ranking-core.json").read_text(encoding="utf-8"))
        compressed_core = json.loads(gzip.decompress((data_dir / "ranking-core.json.gz").read_bytes()))

        self.assertEqual(core, compressed_core)
        self.assertNotIn("recordsByAge", core)
        for age in (item["key"] for item in core["ages"]):
            json_path = data_dir / "ages" / f"{age}.json"
            gzip_path = data_dir / "ages" / f"{age}.json.gz"
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            compressed_payload = json.loads(gzip.decompress(gzip_path.read_bytes()))
            self.assertEqual(payload, compressed_payload)
            self.assertEqual(payload["age"], age)
            self.assertIsInstance(payload["records"], list)

    def test_index_uses_the_generated_data_version(self) -> None:
        index = (WEBAPP_ROOT / "index.html").read_text(encoding="utf-8")
        match = re.search(r'data-data-version="([^"]+)"', index)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), export_data.data_version())
        self.assertNotIn("ranking-data", index)

    def test_legacy_monolithic_assets_are_removed(self) -> None:
        data_dir = WEBAPP_ROOT / "data"

        self.assertFalse((data_dir / "ranking-data.js").exists())
        self.assertFalse((data_dir / "ranking-data.json.gz").exists())

    def test_cache_policy_revalidates_html_and_caches_versioned_assets(self) -> None:
        headers = (WEBAPP_ROOT / "_headers").read_text(encoding="utf-8")

        self.assertIn("/index.html\n  Cache-Control: public, max-age=0, must-revalidate", headers)
        self.assertIn("/src/*\n  Cache-Control: public, max-age=0, must-revalidate", headers)
        self.assertIn("/data/*\n  Cache-Control: public, max-age=31536000, immutable", headers)
        self.assertIn("Content-Security-Policy:", headers)

    def test_strength_filters_are_alphabetical_within_sections(self) -> None:
        index = (WEBAPP_ROOT / "index.html").read_text(encoding="utf-8")
        options = re.search(
            r'<div class="strength-options">(.*?)</div>',
            index,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(options)
        general_options, kit_options = options.group(1).split(
            '<span class="strength-option-group">Kit production</span>',
            maxsplit=1,
        )
        for section in (general_options, kit_options):
            labels = re.findall(r'data-label="([^"]+)"', section)
            self.assertEqual(labels, sorted(labels, key=str.casefold))


if __name__ == "__main__":
    unittest.main()
