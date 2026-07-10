#!/usr/bin/env python3
"""Build the deployable data file for the static Guild Treasury dashboard.

The dashboard deliberately has no build step or server requirement. Run this
script after adding an export to ``input/`` and publish the ``dashboard/``
directory to Cloudflare Pages.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path


AGE_ORDER = [
    "Bronze Age", "Iron Age", "Early Middle Age", "High Middle Age",
    "Late Middle Age", "Colonial Age", "Industrial Age", "Progressive Era",
    "Modern Era", "Postmodern Era", "Contemporary Era", "Tomorrow Era",
    "Future Era", "Arctic Future", "Oceanic Future", "Virtual Future",
    "Space Age Mars", "Space Age Asteroid Belt", "Space Age Venus",
    "Space Age Jupiter Moon", "Space Age Titan", "Space Age Space Hub",
]
BRONZE_GOODS = {"wine", "dye", "marble", "lumber", "stone"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh static dashboard data from a treasury export.")
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--csv", type=Path, help="Use a specific CSV instead of the newest export.")
    parser.add_argument("--output", type=Path, default=Path("dashboard/data.js"))
    parser.add_argument("--guild-name", default="GoE")
    return parser.parse_args()


def newest_csv(input_dir: Path) -> Path:
    files = [path for path in input_dir.glob("*.csv") if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    return max(files, key=lambda path: path.stat().st_mtime)


def parse_date(value: str) -> dt.date:
    value = value.strip()
    if " @ " in value:
        value = value.split(" @ ", 1)[0]
    for pattern in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
        "%d/%b/%y",
    ):
        try:
            return dt.datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported treasury date: {value!r}")


def parse_int(value: str | None) -> int:
    if not value:
        return 0
    return int(value.replace(",", "").strip() or 0)


def read_export(path: Path) -> tuple[list[str], list[tuple[dt.date, dict[str, int]]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = handle.readline()
        handle.seek(0)
        # Treasury exports have used both comma and semicolon delimiters. The
        # header is unambiguous, unlike the many numeric rows below it.
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        date_column = next((name for name in reader.fieldnames if name.strip().lower() in {"date", "datetime"}), reader.fieldnames[0])
        goods = [name for name in reader.fieldnames if name != date_column]
        rows = []
        for row in reader:
            raw_date = (row.get(date_column) or "").strip()
            if raw_date:
                rows.append((parse_date(raw_date), {good: parse_int(row.get(good)) for good in goods}))
    if not rows:
        raise ValueError("CSV contains no data rows")
    return goods, sorted(rows, key=lambda row: row[0])


def age_mapping(goods: list[str]) -> dict[str, str]:
    if len(goods) % 5:
        raise ValueError("Cannot infer goods-to-age mapping: expected groups of five goods.")
    age_offset = len(AGE_ORDER) - len(goods) // 5
    if age_offset < 0:
        raise ValueError("Cannot infer goods-to-age mapping: too many goods columns.")
    return {good: AGE_ORDER[age_offset + index // 5] for index, good in enumerate(goods)}


def main() -> None:
    args = parse_args()
    source = args.csv or newest_csv(args.input_dir)
    goods, rows = read_export(source)
    mapping = age_mapping(goods)
    included_goods = [good for good in goods if good.strip().lower() not in BRONZE_GOODS]
    payload = {
        "meta": {
            "guildName": args.guild_name.strip() or "Guild",
            "firstDate": rows[0][0].isoformat(),
            "latestDate": rows[-1][0].isoformat(),
            "availableDays": len(rows),
            "lowStockThreshold": 110000,
        },
        "dates": [date.isoformat() for date, _ in rows],
        "goods": [
            {"name": good, "age": mapping[good], "values": [values[good] for _, values in rows]}
            for good in included_goods
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("window.TREASURY_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"Dashboard data generated: {args.output}")
    print(f"Source: {source} ({len(rows)} snapshots, {len(included_goods)} non-Bronze goods)")


if __name__ == "__main__":
    main()
