#!/usr/bin/env python3
"""Build Great Building attribute reports from a building_entity_lookup payload."""
from __future__ import annotations

import argparse
import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "output" / "network_cityentities_capture"
GB_IDENTIFIER_PREFIX = "building_entity_X_"


@dataclass(frozen=True)
class LookupEntry:
    cityentity_id: str
    url: str


def fetch_url_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "CityAnalysis/gb-network-script"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()

    if encoding == "gzip" or payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    return payload.decode("utf-8")


def load_lookup_entries(source: str, timeout: float) -> List[Dict[str, Any]]:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        data = json.loads(fetch_url_text(source, timeout=timeout))
    else:
        with open(source, "r", encoding="utf-8") as handle:
            data = json.load(handle)

    if not isinstance(data, list):
        raise SystemExit("Lookup payload must be a JSON list of {identifier, url} objects.")
    return [item for item in data if isinstance(item, dict)]


def extract_gb_lookup_rows(entries: Iterable[Dict[str, Any]]) -> List[LookupEntry]:
    rows: List[LookupEntry] = []
    for item in entries:
        identifier = item.get("identifier")
        url = item.get("url")
        if not isinstance(identifier, str) or not isinstance(url, str):
            continue
        if not identifier.startswith(GB_IDENTIFIER_PREFIX):
            continue
        cityentity_id = identifier.replace("building_entity_", "", 1)
        rows.append(LookupEntry(cityentity_id=cityentity_id, url=url))
    rows.sort(key=lambda row: row.cityentity_id)
    return rows


def write_lookup_tsv(path: Path, rows: Sequence[LookupEntry]) -> None:
    lines = ["cityentity_id\turl"]
    lines.extend(f"{row.cityentity_id}\t{row.url}" for row in rows)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def download_one(url: str, timeout: float) -> str:
    return fetch_url_text(url, timeout=timeout)


def download_metadata_files(
    rows: Sequence[LookupEntry],
    out_dir: Path,
    timeout: float,
    workers: int,
    force_download: bool,
) -> Tuple[int, List[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def save_row(row: LookupEntry) -> Optional[str]:
        target = out_dir / f"{row.cityentity_id}.json"
        if target.exists() and not force_download:
            return None
        payload = download_one(row.url, timeout=timeout)
        target.write_text(payload, encoding="utf-8")
        return row.cityentity_id

    errors: List[str] = []
    downloaded = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(save_row, row): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
                if result is not None:
                    downloaded += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{row.cityentity_id}: {exc}")
    return downloaded, errors


def load_great_buildings_from_files(metadata_dir: Path) -> Dict[str, Dict[str, Any]]:
    gbs: Dict[str, Dict[str, Any]] = {}
    for file_path in sorted(metadata_dir.glob("*.json")):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("type") != "greatbuilding":
            continue
        eid = data.get("id")
        key = eid if isinstance(eid, str) and eid else file_path.stem
        gbs[key] = data
    return gbs


def write_outputs(output_dir: Path, gbs: Dict[str, Dict[str, Any]]) -> None:
    full_path = output_dir / "great_buildings_attributes_from_network.json"
    keys_path = output_dir / "great_buildings_attribute_keys_from_network.txt"
    summary_path = output_dir / "great_buildings_attribute_summary_from_network.tsv"

    full_path.write_text(json.dumps(gbs, ensure_ascii=False, indent=2), encoding="utf-8")

    all_keys = sorted({k for entity in gbs.values() for k in entity.keys()})
    keys_path.write_text("\n".join(all_keys).rstrip() + "\n", encoding="utf-8")

    headers = [
        "id",
        "name",
        "max_tier",
        "min_era",
        "width",
        "length",
        "points",
        "passive_bonus_type",
        "production_bonus_type",
        "abilities_count",
        "strategy_points_for_upgrade_len",
        "top_level_keys",
    ]
    lines = ["\t".join(headers)]

    sorted_rows = sorted(gbs.items(), key=lambda item: item[1].get("name", item[0]))
    for entity_id, entity in sorted_rows:
        requirements = entity.get("requirements") if isinstance(entity.get("requirements"), dict) else {}
        passive_bonus = entity.get("passive_bonus") if isinstance(entity.get("passive_bonus"), dict) else {}
        production_bonus = (
            entity.get("production_bonus") if isinstance(entity.get("production_bonus"), dict) else {}
        )
        abilities = entity.get("abilities") if isinstance(entity.get("abilities"), list) else []
        strategy_points = (
            entity.get("strategy_points_for_upgrade")
            if isinstance(entity.get("strategy_points_for_upgrade"), list)
            else []
        )

        max_tier_obj = entity.get("maxTier")
        if isinstance(max_tier_obj, dict):
            max_tier = str(max_tier_obj.get("value", ""))
        elif max_tier_obj is None:
            max_tier = ""
        else:
            max_tier = str(max_tier_obj)

        row = [
            entity_id,
            str(entity.get("name", "")),
            max_tier,
            str(requirements.get("min_era", "")),
            str(entity.get("width", "")),
            str(entity.get("length", "")),
            str(entity.get("points", "")),
            str(passive_bonus.get("type", "")),
            str(production_bonus.get("type", "")),
            str(len(abilities)),
            str(len(strategy_points)),
            "|".join(sorted(entity.keys())),
        ]
        lines.append("\t".join(row))

    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Great Building attributes from building_entity_lookup payload."
    )
    parser.add_argument(
        "--lookup-source",
        required=True,
        help="Lookup JSON source: local file path or https URL to building_entity_lookup payload.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel download workers. Default: 8",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout seconds. Default: 30",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download metadata even if per-entity JSON already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir = output_dir / "great_building_metadata"

    lookup_entries = load_lookup_entries(args.lookup_source, timeout=args.timeout)
    gb_rows = extract_gb_lookup_rows(lookup_entries)
    if not gb_rows:
        raise SystemExit("No Great Building entries found (identifier prefix building_entity_X_).")

    tsv_path = output_dir / "great_building_metadata_urls.tsv"
    write_lookup_tsv(tsv_path, gb_rows)

    downloaded, errors = download_metadata_files(
        rows=gb_rows,
        out_dir=metadata_dir,
        timeout=args.timeout,
        workers=args.workers,
        force_download=args.force_download,
    )
    if errors:
        error_path = output_dir / "great_building_download_errors.txt"
        error_path.write_text("\n".join(errors).rstrip() + "\n", encoding="utf-8")
    gbs = load_great_buildings_from_files(metadata_dir)
    if not gbs:
        raise SystemExit("No greatbuilding payloads found in downloaded metadata files.")

    write_outputs(output_dir, gbs)

    print(f"Lookup source: {args.lookup_source}")
    print(f"GB URLs: {len(gb_rows)}")
    print(f"Downloaded now: {downloaded}")
    print(f"GB attributes parsed: {len(gbs)}")
    print(f"Output directory: {output_dir}")
    if errors:
        print(f"Download errors: {len(errors)} (see {output_dir / 'great_building_download_errors.txt'})")


if __name__ == "__main__":
    main()
