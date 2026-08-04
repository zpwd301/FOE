#!/usr/bin/env python3
"""Build the static contribution-record data used by the GoE Guild Portal."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

from build_dashboard import DEFAULT_CONTRIBUTION_DATA_SOURCE, publish_dashboard


REQUIRED_COLUMNS = (
    "Player ID",
    "Player name",
    "Era",
    "Good",
    "Amount",
    "Message",
    "Date/Time",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh static guild-contribution data from a GuildTreasury export."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("input/guild-goods-contribution"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Use only this CSV instead of merging every export in the input directory.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_CONTRIBUTION_DATA_SOURCE)
    parser.add_argument("--guild-name", default="GoE")
    return parser.parse_args()


def contribution_csvs(input_dir: Path) -> list[Path]:
    files = [path for path in input_dir.glob("*.csv") if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name))


def parse_timestamp(value: str) -> dt.datetime:
    for pattern in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return dt.datetime.strptime(value.strip(), pattern)
        except ValueError:
            pass
    raise ValueError(f"Unsupported contribution date/time: {value!r}")


def parse_amount(value: str) -> int:
    return int(value.replace(",", "").strip())


def read_export(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = handle.readline()
        handle.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("Contribution CSV has no header row")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Contribution CSV is missing columns: {', '.join(missing)}")

        rows: list[dict[str, object]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp = parse_timestamp(row["Date/Time"] or "")
                amount = parse_amount(row["Amount"] or "")
            except ValueError as error:
                raise ValueError(f"Invalid contribution row {line_number}: {error}") from error
            rows.append(
                {
                    "timestamp": timestamp,
                    "playerId": (row["Player ID"] or "").strip(),
                    "playerName": (row["Player name"] or "Unknown player").strip(),
                    "era": (row["Era"] or "Unknown era").strip(),
                    "good": (row["Good"] or "Unknown good").strip(),
                    "amount": amount,
                    "message": (row["Message"] or "Unspecified").strip(),
                }
            )
    if not rows:
        raise ValueError("Contribution CSV contains no data rows")
    return sorted(rows, key=lambda row: row["timestamp"], reverse=True)


def record_key(row: dict[str, object]) -> tuple[object, ...]:
    """Identify one transaction without depending on a player's display name."""
    player = str(row["playerId"]) or str(row["playerName"])
    return (
        player,
        row["era"],
        row["good"],
        row["amount"],
        row["message"],
        row["timestamp"],
    )


def merge_exports(paths: list[Path]) -> tuple[list[dict[str, object]], int]:
    """Merge non-cumulative, potentially overlapping exports deterministically."""
    records_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    input_count = 0
    for path in paths:
        for row in read_export(path):
            input_count += 1
            # Paths are oldest to newest, so a later snapshot supplies the most
            # current display name if the same transaction appears more than once.
            records_by_key[record_key(row)] = row
    rows = sorted(records_by_key.values(), key=lambda row: row["timestamp"], reverse=True)
    return rows, input_count - len(rows)


def build_payload(
    rows: list[dict[str, object]],
    guild_name: str,
    *,
    source_files: list[Path] | None = None,
    duplicate_count: int = 0,
) -> dict[str, object]:
    timestamps = [row["timestamp"] for row in rows]
    first = min(timestamps)
    latest = max(timestamps)
    player_ids = {str(row["playerId"]) for row in rows}
    return {
        "meta": {
            "guildName": guild_name.strip() or "Guild",
            "firstTimestamp": first.isoformat(timespec="seconds"),
            "latestTimestamp": latest.isoformat(timespec="seconds"),
            "availableDays": (latest.date() - first.date()).days + 1,
            "recordCount": len(rows),
            "playerCount": len(player_ids),
            "sourceFileCount": len(source_files or []),
            "sourceFiles": [path.name for path in source_files or []],
            "duplicateRecordCount": duplicate_count,
        },
        # Compact arrays keep the no-runtime static payload substantially smaller.
        "records": [
            [
                row["timestamp"].isoformat(timespec="seconds"),
                row["playerId"],
                row["playerName"],
                row["era"],
                row["good"],
                row["amount"],
                row["message"],
            ]
            for row in rows
        ],
    }


def main() -> None:
    args = parse_args()
    sources = [args.csv] if args.csv else contribution_csvs(args.input_dir)
    rows, duplicate_count = merge_exports(sources)
    payload = build_payload(
        rows,
        args.guild_name,
        source_files=sources,
        duplicate_count=duplicate_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "window.CONTRIBUTION_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    assets = publish_dashboard(contribution_data_source=args.output)
    positive_count = sum(1 for row in rows if int(row["amount"]) > 0)
    negative_count = sum(1 for row in rows if int(row["amount"]) < 0)
    print(f"Contribution data generated: {args.output}")
    print("Published assets: " + ", ".join(path.name for path in assets.values()))
    print(
        f"Sources: {len(sources)} CSV files, {len(rows)} unique records, "
        f"{duplicate_count} duplicates removed "
        f"({positive_count} positive, {negative_count} negative)"
    )


if __name__ == "__main__":
    main()
