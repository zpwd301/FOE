#!/usr/bin/env python3
"""Build the static contribution-record data used by the GoE Guild Portal."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
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
TRANSACTION_ID_COLUMN = "Transaction ID"


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
                    "transactionId": (row.get(TRANSACTION_ID_COLUMN) or "").strip(),
                }
            )
    if not rows:
        raise ValueError("Contribution CSV contains no data rows")
    return sorted(rows, key=lambda row: row["timestamp"], reverse=True)


def record_key(row: dict[str, object]) -> tuple[object, ...]:
    """Return the strongest transaction signature available in an export."""
    player = str(row["playerId"]) or str(row["playerName"])
    visible_signature = (
        player,
        row["era"],
        row["good"],
        row["amount"],
        row["message"],
        row["timestamp"],
    )
    transaction_id = str(row.get("transactionId") or "")
    if transaction_id:
        # Some game events may share a batch ID across multiple goods, so retain
        # the visible signature as part of the key instead of trusting the ID alone.
        return ("transaction-id", transaction_id, *visible_signature)
    return ("legacy-signature", *visible_signature)


def production_context(row: dict[str, object]) -> tuple[object, ...] | None:
    """Identify one contiguous building-production group in Forge Hammer order."""
    if row["message"] != "Building production" or row.get("transactionId"):
        return None
    player = str(row["playerId"]) or str(row["playerName"])
    return (player, row["era"], row["message"], row["timestamp"])


def malformed_production_indexes(rows: list[dict[str, object]]) -> set[int]:
    """Find impossible five-good batches caused by unstable offset pagination.

    A guild building production posts one equal amount for each of an era's five
    goods. When new log entries shift offset pagination during an export, the end
    of one page can be spliced onto the start of another and create a mixed-amount
    five-good batch. Runs may begin partway through a real batch, so choose the
    alignment that preserves the most complete, uniform batches before rejecting
    only complete five-good batches with mixed amounts.
    """
    malformed: set[int] = set()
    index = 0
    while index < len(rows):
        context = production_context(rows[index])
        if context is None:
            index += 1
            continue
        end = index + 1
        while end < len(rows) and production_context(rows[end]) == context:
            end += 1

        run_length = end - index
        best_alignment = 0
        best_score: tuple[int, int, int] | None = None
        for alignment in range(min(5, run_length + 1)):
            uniform_count = 0
            complete_count = 0
            for batch_start in range(index + alignment, end - 4, 5):
                batch = rows[batch_start : batch_start + 5]
                if len({row["good"] for row in batch}) != 5:
                    continue
                complete_count += 1
                if len({row["amount"] for row in batch}) == 1:
                    uniform_count += 1
            score = (uniform_count, complete_count, -alignment)
            if best_score is None or score > best_score:
                best_score = score
                best_alignment = alignment

        for batch_start in range(index + best_alignment, end - 4, 5):
            batch = rows[batch_start : batch_start + 5]
            if (
                len({row["good"] for row in batch}) == 5
                and len({row["amount"] for row in batch}) > 1
            ):
                malformed.update(range(batch_start, batch_start + 5))
        index = end
    return malformed


def merge_exports(paths: list[Path]) -> tuple[list[dict[str, object]], int]:
    """Merge overlapping exports without collapsing repeated real transactions.

    Legacy Forge Hammer CSVs do not contain a transaction ID. For those files,
    identical rows are treated as a multiset: the merged occurrence count is the
    largest count present in any source snapshot. Impossible mixed-amount legacy
    production batches are rejected as offset-pagination splices. Rows with a
    transaction ID are exact-deduplicated within and across exports.
    """
    merged_counts: Counter[tuple[object, ...]] = Counter()
    latest_rows: dict[tuple[object, ...], dict[str, object]] = {}
    input_count = 0
    for path in paths:
        source_counts: Counter[tuple[object, ...]] = Counter()
        source_rows = read_export(path)
        input_count += len(source_rows)
        malformed_indexes = malformed_production_indexes(source_rows)
        for row_index, row in enumerate(source_rows):
            if row_index in malformed_indexes:
                continue
            key = record_key(row)
            if row.get("transactionId"):
                source_counts[key] = 1
            else:
                source_counts[key] += 1
            # Paths are oldest to newest, so a later snapshot supplies the most
            # current display name for every occurrence of an overlapping row.
            latest_rows[key] = row
        merged_counts |= source_counts

    rows = [
        latest_rows[key].copy()
        for key, count in merged_counts.items()
        for _ in range(count)
    ]
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
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
        f"Sources: {len(sources)} CSV files, {len(rows)} merged transaction rows, "
        f"{duplicate_count} overlapping or malformed copies removed "
        f"({positive_count} positive, {negative_count} negative)"
    )


if __name__ == "__main__":
    main()
