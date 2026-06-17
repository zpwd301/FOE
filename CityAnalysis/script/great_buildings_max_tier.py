#!/usr/bin/env python3
"""Export Great Buildings and their max tiers from a city JSON snapshot."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from glob import glob
from typing import Any, Dict, List, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def latest_city_file() -> str:
    files = glob(os.path.join(INPUT_DIR, "city_*.json"))
    if not files:
        raise SystemExit(f"No city JSON files found in {INPUT_DIR}")
    return max(files, key=os.path.getmtime)


def load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    if isinstance(raw, dict):
        return raw
    raise SystemExit("Unexpected JSON payload format")


def extract_rows(entities: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for entry in entities.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "greatbuilding":
            continue
        max_tier = entry.get("maxTier")
        tier = max_tier.get("value") if isinstance(max_tier, dict) else max_tier
        tier_text = tier if isinstance(tier, str) else ""
        name = entry.get("name") or entry.get("id") or ""
        rows.append((tier_text, str(name)))
    rows.sort(key=lambda item: (item[0], item[1]))
    return rows


def write_report(path: str, rows: List[Tuple[str, str]]) -> None:
    lines = ["max_tier\tname"]
    lines.extend(f"{tier}\t{name}" for tier, name in rows)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export great buildings and max tiers")
    parser.add_argument(
        "--input",
        default=None,
        help="Input city JSON path. Default: latest city_*.json in input/.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. Default: output/great_buildings_max_tier_<timestamp>.txt",
    )
    args = parser.parse_args()

    input_path = args.input or latest_city_file()
    payload = load_payload(input_path)
    entities = payload.get("CityEntities")
    if not isinstance(entities, dict):
        raise SystemExit("CityEntities not found in JSON")

    rows = extract_rows(entities)
    output_path = args.output
    if not output_path:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(OUTPUT_DIR, f"great_buildings_max_tier_{stamp}.txt")
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    write_report(output_path, rows)
    print(f"Source: {input_path}")
    print(f"Rows: {len(rows)}")
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()
