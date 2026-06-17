#!/usr/bin/env python3
"""Compare two us24 Arc scan TSVs and emit a structured diff."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "us24_arc_rank_scan"
SCAN_GLOB = "us24_arc_level_scan_first_50_pages_*.tsv"
FIELDS = ["page", "rank", "player_name", "guild_name", "arc_level", "requiredPoints"]
SIGNIFICANT_FIELDS = ["arc_level"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two us24 Arc scan TSVs. "
            "Only Arc level changes count as CHANGED; page, rank, guild, and requiredPoints are ignored."
        )
    )
    parser.add_argument(
        "--old-file",
        default="",
        help="Older scan TSV. Default: second-most-recent matching scan file.",
    )
    parser.add_argument(
        "--new-file",
        default="",
        help="Newer scan TSV. Default: most-recent matching scan file.",
    )
    parser.add_argument(
        "--output-tsv",
        default="",
        help="Optional output TSV path. Default: output/us24_arc_rank_scan/<timestamped diff>.tsv",
    )
    return parser.parse_args()


def pick_default_files() -> tuple[Path, Path]:
    files = sorted(
        (
            path
            for path in OUTPUT_DIR.glob(SCAN_GLOB)
            if "_vs_" not in path.name and "_diff_" not in path.name
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if len(files) < 2:
        raise SystemExit(f"Need at least 2 scan files under {OUTPUT_DIR}")
    return files[1].resolve(), files[0].resolve()


def resolve_input_file(path_arg: str) -> Path:
    path = Path(path_arg).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")
    return path


def resolve_output_path(path_arg: str) -> Path:
    path = Path(path_arg).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def load_scan(path: Path) -> Dict[str, Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            name = row["player_name"].strip()
            if name in rows:
                raise SystemExit(f"Duplicate player_name in {path}: {name}")
            rows[name] = {field: row.get(field, "").strip() for field in FIELDS}
    return rows


def build_default_output_path(old_file: Path, new_file: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return (
        OUTPUT_DIR
        / f"{old_file.stem}_vs_{new_file.stem}_diff_{stamp}.tsv"
    ).resolve()


def has_significant_change(old_row: Dict[str, str], new_row: Dict[str, str]) -> bool:
    return any(old_row[field] != new_row[field] for field in SIGNIFICANT_FIELDS)


def sort_rank(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 10**9


def main() -> None:
    args = parse_args()
    if args.old_file and args.new_file:
        old_file = resolve_input_file(args.old_file)
        new_file = resolve_input_file(args.new_file)
    elif not args.old_file and not args.new_file:
        old_file, new_file = pick_default_files()
    else:
        raise SystemExit("Provide both --old-file and --new-file, or neither.")

    old_scan = load_scan(old_file)
    new_scan = load_scan(new_file)

    output_path = (
        resolve_output_path(args.output_tsv)
        if args.output_tsv
        else build_default_output_path(old_file, new_file)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    diff_rows: List[Dict[str, str]] = []
    counts = {"ADDED": 0, "REMOVED": 0, "CHANGED": 0}

    for player_name in sorted(set(old_scan) | set(new_scan), key=str.casefold):
        old_row = old_scan.get(player_name)
        new_row = new_scan.get(player_name)

        if old_row is None:
            counts["ADDED"] += 1
            diff_rows.append(
                {
                    "change_type": "ADDED",
                    "player_name": player_name,
                    "old_page": "",
                    "new_page": new_row["page"],
                    "old_rank": "",
                    "new_rank": new_row["rank"],
                    "old_guild_name": "",
                    "new_guild_name": new_row["guild_name"],
                    "old_arc_level": "",
                    "new_arc_level": new_row["arc_level"],
                    "old_requiredPoints": "",
                    "new_requiredPoints": new_row["requiredPoints"],
                }
            )
            continue

        if new_row is None:
            counts["REMOVED"] += 1
            diff_rows.append(
                {
                    "change_type": "REMOVED",
                    "player_name": player_name,
                    "old_page": old_row["page"],
                    "new_page": "",
                    "old_rank": old_row["rank"],
                    "new_rank": "",
                    "old_guild_name": old_row["guild_name"],
                    "new_guild_name": "",
                    "old_arc_level": old_row["arc_level"],
                    "new_arc_level": "",
                    "old_requiredPoints": old_row["requiredPoints"],
                    "new_requiredPoints": "",
                }
            )
            continue

        if not has_significant_change(old_row, new_row):
            continue

        counts["CHANGED"] += 1
        diff_rows.append(
            {
                "change_type": "CHANGED",
                "player_name": player_name,
                "old_page": old_row["page"],
                "new_page": new_row["page"],
                "old_rank": old_row["rank"],
                "new_rank": new_row["rank"],
                "old_guild_name": old_row["guild_name"],
                "new_guild_name": new_row["guild_name"],
                "old_arc_level": old_row["arc_level"],
                "new_arc_level": new_row["arc_level"],
                "old_requiredPoints": old_row["requiredPoints"],
                "new_requiredPoints": new_row["requiredPoints"],
            }
        )

    change_order = {"ADDED": 0, "REMOVED": 1, "CHANGED": 2}
    diff_rows.sort(
        key=lambda row: (
            change_order[row["change_type"]],
            sort_rank(row["new_rank"] or row["old_rank"]),
            row["player_name"].casefold(),
        )
    )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "change_type",
                "player_name",
                "old_page",
                "new_page",
                "old_rank",
                "new_rank",
                "old_guild_name",
                "new_guild_name",
                "old_arc_level",
                "new_arc_level",
                "old_requiredPoints",
                "new_requiredPoints",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(diff_rows)

    print(f"Old file: {old_file}")
    print(f"New file: {new_file}")
    print(f"Old count: {len(old_scan)}")
    print(f"New count: {len(new_scan)}")
    print(f"Added: {counts['ADDED']}")
    print(f"Removed: {counts['REMOVED']}")
    print(f"Changed: {counts['CHANGED']}")
    print(f"Diff TSV: {output_path}")


if __name__ == "__main__":
    main()
