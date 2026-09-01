from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT_DIR = WEBAPP_ROOT / "scripts"
sys.path.insert(0, str(EXPORT_SCRIPT_DIR))

import export_data  # noqa: E402


class ExportAssetTests(unittest.TestCase):
    @staticmethod
    def read_brotli_json(path: Path):
        executable = shutil.which("brotli")
        if executable is None:
            raise AssertionError("The brotli executable is required to validate export assets.")
        result = subprocess.run(
            [executable, "-d", "-c", str(path)],
            check=True,
            stdout=subprocess.PIPE,
        )
        return json.loads(result.stdout)

    @staticmethod
    def age_variant(index: dict, entity_id: str, age: str, fallback):
        entry = index.get(entity_id)
        if not isinstance(entry, dict):
            return fallback
        overrides = entry.get("overrides", {})
        return overrides.get(age, entry.get("default", fallback))

    def test_default_age_is_space_age_asteroid_belt(self) -> None:
        data_dir = WEBAPP_ROOT / "data"
        core = json.loads((data_dir / "ranking-core.json").read_text(encoding="utf-8"))

        self.assertEqual(core["metadata"]["defaultAge"], "SpaceAgeAsteroidBelt")

    def test_core_and_every_age_have_matching_json_gzip_and_brotli(self) -> None:
        data_dir = WEBAPP_ROOT / "data"
        core = json.loads((data_dir / "ranking-core.json").read_text(encoding="utf-8"))
        compressed_core = json.loads(gzip.decompress((data_dir / "ranking-core.json.gz").read_bytes()))
        brotli_core = self.read_brotli_json(data_dir / "ranking-core.json.br")

        self.assertEqual(core, compressed_core)
        self.assertEqual(core, brotli_core)
        self.assertNotIn("recordsByAge", core)
        self.assertNotIn("cityRecordsByAge", core)
        ranking_record_count = 0
        city_record_count = 0
        for age in (item["key"] for item in core["ages"]):
            payloads = {}
            for directory in ("ages", "city-ages"):
                json_path = data_dir / directory / f"{age}.json"
                gzip_path = data_dir / directory / f"{age}.json.gz"
                brotli_path = data_dir / directory / f"{age}.json.br"
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                gzip_payload = json.loads(gzip.decompress(gzip_path.read_bytes()))
                brotli_payload = self.read_brotli_json(brotli_path)
                self.assertEqual(payload, gzip_payload)
                self.assertEqual(payload, brotli_payload)
                self.assertEqual(payload["age"], age)
                self.assertIsInstance(payload["records"], list)
                payloads[directory] = payload
            ranking_ids = {record["entityId"] for record in payloads["ages"]["records"]}
            city_ids = {record["entityId"] for record in payloads["city-ages"]["records"]}
            self.assertTrue(ranking_ids.issubset(city_ids))
            ranking_record_count += len(payloads["ages"]["records"])
            city_record_count += len(payloads["city-ages"]["records"])
        self.assertGreater(city_record_count, ranking_record_count)

    def test_index_uses_the_generated_data_version(self) -> None:
        index = (WEBAPP_ROOT / "index.html").read_text(encoding="utf-8")
        match = re.search(r'data-data-version="([^"]+)"', index)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), export_data.data_version())
        self.assertNotIn("ranking-data", index)

    def test_unit_details_match_exported_ranking_attributes(self) -> None:
        data_dir = WEBAPP_ROOT / "data"
        core = json.loads((data_dir / "ranking-core.json").read_text(encoding="utf-8"))
        index = core["unitProductionByEntity"]
        attribute_keys = {
            "prod_unit_current_age",
            "prod_unit_next_age",
            "prod_unit_rogue",
        }

        for age in (item["key"] for item in core["ages"]):
            payload = json.loads((data_dir / "ages" / f"{age}.json").read_text(encoding="utf-8"))
            for record in payload["records"]:
                details = self.age_variant(index, record["entityId"], age, [])
                for attribute_key in attribute_keys:
                    expected = sum(
                        float(item["expectedPerDay"])
                        for item in details
                        if item["attributeKey"] == attribute_key
                    )
                    actual = float(record.get("attrs", {}).get(attribute_key, 0.0))
                    self.assertAlmostEqual(actual, expected, places=9)

    def test_legacy_monolithic_assets_are_removed(self) -> None:
        data_dir = WEBAPP_ROOT / "data"

        self.assertFalse((data_dir / "ranking-data.js").exists())
        self.assertFalse((data_dir / "ranking-data.json.gz").exists())

    def test_cache_policy_revalidates_html_and_caches_versioned_assets(self) -> None:
        headers = (WEBAPP_ROOT / "_headers").read_text(encoding="utf-8")

        self.assertIn("/index.html\n  Cache-Control: public, max-age=0, must-revalidate", headers)
        self.assertIn("/src/*\n  Cache-Control: public, max-age=0, must-revalidate", headers)
        self.assertIn("/data/*\n  Cache-Control: public, max-age=31536000, immutable", headers)
        self.assertIn("/data/ages/*.json.br\n  Content-Encoding: br", headers)
        self.assertIn("/data/city-ages/*.json.br\n  Content-Encoding: br", headers)
        self.assertIn("/data/ages/*.json.gz\n  Content-Encoding: gzip", headers)
        self.assertIn("/data/city-ages/*.json.gz\n  Content-Encoding: gzip", headers)
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
