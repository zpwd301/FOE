#!/usr/bin/env python3
"""Build the static contribution-record data used by the GoE Guild Portal."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Sequence

from build_dashboard import DEFAULT_CONTRIBUTION_DATA_SOURCE, publish_dashboard
from generate_treasury_dashboard import age_mapping, read_export as read_treasury_export


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
CONTRIBUTION_DATA_PREFIX = "window.CONTRIBUTION_DATA = "
CONTRIBUTION_FILENAME_RE = re.compile(r"^GuildTreasury-(\d{4}-\d{2}-\d{2})\.csv$")


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
    parser.add_argument(
        "--audit-baseline-contribution",
        type=Path,
        help=(
            "Use this earlier contribution capture as the closed-history baseline for "
            "the newest CSV. Requires both treasury audit arguments."
        ),
    )
    parser.add_argument(
        "--audit-baseline-treasury",
        type=Path,
        help="Treasury snapshot paired with --audit-baseline-contribution.",
    )
    parser.add_argument(
        "--audit-current-treasury",
        type=Path,
        help="Treasury snapshot paired with the newest contribution CSV.",
    )
    return parser.parse_args()


def contribution_csvs(input_dir: Path) -> list[Path]:
    files = [path for path in input_dir.glob("*.csv") if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    return sorted(files, key=contribution_file_sort_key)


def contribution_file_sort_key(path: Path) -> tuple[str, int, str]:
    match = CONTRIBUTION_FILENAME_RE.fullmatch(path.name)
    export_date = match.group(1) if match else ""
    return export_date, path.stat().st_mtime_ns, path.name


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


def normalized_export(path: Path) -> tuple[list[dict[str, object]], int]:
    """Read one export, rejecting malformed batches and exact ID duplicates."""
    source_rows = read_export(path)
    malformed_indexes = malformed_production_indexes(source_rows)
    rows: list[dict[str, object]] = []
    seen_transaction_keys: set[tuple[object, ...]] = set()
    for row_index, row in enumerate(source_rows):
        if row_index in malformed_indexes:
            continue
        if row.get("transactionId"):
            key = record_key(row)
            if key in seen_transaction_keys:
                continue
            seen_transaction_keys.add(key)
        rows.append(row)
    return rows, len(source_rows) - len(rows)


def reconcile_closed_history(
    baseline_rows: Sequence[dict[str, object]],
    current_rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], dt.datetime]:
    """Keep the prior capture immutable and append only newly timed records.

    Forge Hammer's offset pages can return different multiplicities for tied,
    indistinguishable historical rows. The earlier capture is authoritative for
    its closed time window; only rows strictly newer than its high-water mark can
    enter from the later capture.
    """
    if not baseline_rows:
        raise ValueError("Contribution audit baseline contains no valid records")
    cutoff = max(row["timestamp"] for row in baseline_rows)
    rows = [row.copy() for row in baseline_rows]
    rows.extend(
        row.copy() for row in current_rows if row["timestamp"] > cutoff
    )
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    return rows, cutoff


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_inventory_delta(
    baseline_contribution: Path,
    current_contribution: Path,
    baseline_treasury: Path,
    current_treasury: Path,
) -> dict[str, object]:
    """Prove that signed log changes equal treasury changes for every good."""
    baseline_rows, _ = normalized_export(baseline_contribution)
    current_rows, _ = normalized_export(current_contribution)
    _, cutoff = reconcile_closed_history(baseline_rows, current_rows)

    baseline_goods, baseline_snapshots = read_treasury_export(baseline_treasury)
    current_goods, current_snapshots = read_treasury_export(current_treasury)
    baseline_inventory = baseline_snapshots[-1][1]
    current_inventory = current_snapshots[-1][1]
    if not set(baseline_goods).issubset(current_goods):
        removed = sorted(set(baseline_goods) - set(current_goods))
        raise ValueError(
            "All-goods inventory audit cannot continue because goods disappeared: "
            + ", ".join(removed)
        )

    contribution_delta: Counter[str] = Counter()
    for row in current_rows:
        if row["timestamp"] > cutoff:
            contribution_delta[str(row["good"])] += int(row["amount"])

    mapping = age_mapping(current_goods)
    per_age: dict[str, dict[str, int]] = {}
    mismatches: list[dict[str, object]] = []
    for good in current_goods:
        inventory_change = current_inventory.get(good, 0) - baseline_inventory.get(good, 0)
        logged_change = contribution_delta[good]
        age = mapping[good]
        totals = per_age.setdefault(
            age,
            {"goodsChecked": 0, "inventoryDelta": 0, "contributionDelta": 0},
        )
        totals["goodsChecked"] += 1
        totals["inventoryDelta"] += inventory_change
        totals["contributionDelta"] += logged_change
        if inventory_change != logged_change:
            mismatches.append(
                {
                    "age": age,
                    "good": good,
                    "inventoryDelta": inventory_change,
                    "contributionDelta": logged_change,
                    "difference": inventory_change - logged_change,
                }
            )

    unknown_logged_goods = sorted(set(contribution_delta) - set(current_goods))
    if unknown_logged_goods:
        raise ValueError(
            "All-goods inventory audit found contribution goods absent from treasury: "
            + ", ".join(unknown_logged_goods)
        )
    if mismatches:
        examples = "; ".join(
            f"{item['good']} ({int(item['difference']):+d})"
            for item in mismatches[:10]
        )
        raise ValueError(
            f"All-goods inventory audit failed for {len(mismatches)} of "
            f"{len(current_goods)} goods after {cutoff.isoformat(sep=' ')}: {examples}"
        )

    return {
        "status": "passed",
        "cutoffTimestamp": cutoff.isoformat(timespec="seconds"),
        "goodsChecked": len(current_goods),
        "agesChecked": len(per_age),
        "baselineContribution": baseline_contribution.name,
        "currentContribution": current_contribution.name,
        "baselineTreasury": baseline_treasury.name,
        "currentTreasury": current_treasury.name,
        "baselineContributionSha256": file_sha256(baseline_contribution),
        "currentContributionSha256": file_sha256(current_contribution),
        "baselineTreasurySha256": file_sha256(baseline_treasury),
        "currentTreasurySha256": file_sha256(current_treasury),
        "perAge": [
            {"age": age, **totals}
            for age, totals in per_age.items()
        ],
    }


def merge_exports(
    paths: list[Path],
    *,
    closed_history_baseline: Path | None = None,
) -> tuple[list[dict[str, object]], int]:
    """Merge overlapping exports without collapsing repeated real transactions.

    Legacy Forge Hammer CSVs do not contain a transaction ID. For those files,
    identical rows are treated as a multiset: the merged occurrence count is the
    largest count present in any source snapshot. Impossible mixed-amount legacy
    production batches are rejected as offset-pagination splices. Rows with a
    transaction ID are exact-deduplicated within and across exports.
    """
    merged_counts: Counter[tuple[object, ...]] = Counter()
    latest_rows: dict[tuple[object, ...], dict[str, object]] = {}
    latest_names: dict[str, str] = {}
    input_count = 0
    for path_index, path in enumerate(paths):
        source_counts: Counter[tuple[object, ...]] = Counter()
        raw_rows = read_export(path)
        input_count += len(raw_rows)
        for row in raw_rows:
            player_id = str(row["playerId"])
            if player_id:
                latest_names[player_id] = str(row["playerName"])
        source_rows, _ = normalized_export(path)
        if closed_history_baseline is not None and path_index == len(paths) - 1:
            baseline_rows, _ = normalized_export(closed_history_baseline)
            source_rows, _ = reconcile_closed_history(baseline_rows, source_rows)
        for row in source_rows:
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
    for row in rows:
        player_id = str(row["playerId"])
        if player_id in latest_names:
            row["playerName"] = latest_names[player_id]
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    return rows, input_count - len(rows)


def build_payload(
    rows: list[dict[str, object]],
    guild_name: str,
    *,
    source_files: list[Path] | None = None,
    duplicate_count: int = 0,
    inventory_audit: dict[str, object] | None = None,
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
            "inventoryAudit": inventory_audit,
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


def treasury_path_for_contribution(contribution_path: Path, treasury_dir: Path) -> Path:
    match = CONTRIBUTION_FILENAME_RE.fullmatch(contribution_path.name)
    if not match:
        raise ValueError(
            f"Cannot infer treasury audit date from {contribution_path.name}"
        )
    return treasury_dir / f"stats-{match.group(1)}.csv"


def resolve_audit_files(
    args: argparse.Namespace,
    sources: list[Path],
) -> tuple[Path, Path, Path, Path] | None:
    explicit = (
        args.audit_baseline_contribution,
        args.audit_baseline_treasury,
        args.audit_current_treasury,
    )
    if any(explicit):
        if not all(explicit):
            raise ValueError(
                "Contribution audit requires --audit-baseline-contribution, "
                "--audit-baseline-treasury, and --audit-current-treasury together"
            )
        return (
            args.audit_baseline_contribution,
            sources[-1],
            args.audit_baseline_treasury,
            args.audit_current_treasury,
        )
    if args.csv:
        return None
    if len(sources) < 2:
        raise ValueError(
            "All-goods inventory audit requires at least two contribution exports"
        )
    baseline_contribution, current_contribution = sources[-2:]
    treasury_dir = args.input_dir.parent
    baseline_treasury = treasury_path_for_contribution(
        baseline_contribution,
        treasury_dir,
    )
    current_treasury = treasury_path_for_contribution(current_contribution, treasury_dir)
    missing = [
        str(path)
        for path in (baseline_treasury, current_treasury)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "All-goods inventory audit is missing treasury snapshots: "
            + ", ".join(missing)
        )
    return (
        baseline_contribution,
        current_contribution,
        baseline_treasury,
        current_treasury,
    )


def read_existing_payload(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw.startswith(CONTRIBUTION_DATA_PREFIX) or not raw.endswith(";"):
        return None
    payload = json.loads(raw[len(CONTRIBUTION_DATA_PREFIX) : -1])
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        return None
    return payload


def payload_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in payload.get("records", []):
        if not isinstance(record, list) or len(record) != 7:
            raise ValueError("Existing contribution payload has an invalid record")
        rows.append(
            {
                "timestamp": dt.datetime.fromisoformat(str(record[0])),
                "playerId": str(record[1]),
                "playerName": str(record[2]),
                "era": str(record[3]),
                "good": str(record[4]),
                "amount": int(record[5]),
                "message": str(record[6]),
                "transactionId": "",
            }
        )
    if not rows:
        raise ValueError("Existing contribution payload contains no records")
    return rows


def cached_audit_matches(
    payload: dict[str, object] | None,
    contribution_path: Path,
    treasury_path: Path,
) -> bool:
    if payload is None:
        return False
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return False
    audit = meta.get("inventoryAudit")
    return bool(
        isinstance(audit, dict)
        and audit.get("status") == "passed"
        and audit.get("currentContributionSha256") == file_sha256(contribution_path)
        and audit.get("currentTreasurySha256") == file_sha256(treasury_path)
    )


def append_audited_rows(
    existing_payload: dict[str, object],
    current_contribution: Path,
    cutoff: dt.datetime,
) -> list[dict[str, object]]:
    """Extend a previously audited canonical payload without reopening history."""
    rows = payload_rows(existing_payload)
    latest = max(row["timestamp"] for row in rows)
    if latest != cutoff:
        raise ValueError(
            "Existing audited contribution history does not end at the audit baseline "
            f"({latest.isoformat(sep=' ')} != {cutoff.isoformat(sep=' ')})"
        )
    current_rows, _ = normalized_export(current_contribution)
    latest_names = {
        str(row["playerId"]): str(row["playerName"])
        for row in current_rows
        if str(row["playerId"])
    }
    for row in rows:
        player_id = str(row["playerId"])
        if player_id in latest_names:
            row["playerName"] = latest_names[player_id]
    rows.extend(row.copy() for row in current_rows if row["timestamp"] > cutoff)
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    return rows


def main() -> None:
    args = parse_args()
    sources = [args.csv] if args.csv else contribution_csvs(args.input_dir)
    audit_files = resolve_audit_files(args, sources)
    existing_payload = read_existing_payload(args.output)
    inventory_audit: dict[str, object] | None = None
    rows: list[dict[str, object]]
    duplicate_count: int

    if audit_files is None:
        rows, duplicate_count = merge_exports(sources)
    else:
        (
            baseline_contribution,
            current_contribution,
            baseline_treasury,
            current_treasury,
        ) = audit_files
        explicit_baseline = args.audit_baseline_contribution is not None
        if (
            not explicit_baseline
            and cached_audit_matches(
                existing_payload,
                current_contribution,
                current_treasury,
            )
        ):
            rows = payload_rows(existing_payload)
            meta = existing_payload["meta"]
            inventory_audit = dict(meta["inventoryAudit"])
            duplicate_count = int(meta.get("duplicateRecordCount", 0))
            print(
                f"All-goods inventory audit already passed for {current_contribution.name}; "
                "reusing canonical history."
            )
        else:
            inventory_audit = audit_inventory_delta(
                baseline_contribution,
                current_contribution,
                baseline_treasury,
                current_treasury,
            )
            if (
                not explicit_baseline
                and cached_audit_matches(
                    existing_payload,
                    baseline_contribution,
                    baseline_treasury,
                )
            ):
                cutoff = dt.datetime.fromisoformat(
                    str(inventory_audit["cutoffTimestamp"])
                )
                rows = append_audited_rows(
                    existing_payload,
                    current_contribution,
                    cutoff,
                )
                old_meta = existing_payload["meta"]
                raw_current_count = len(read_export(current_contribution))
                added_count = sum(1 for row in rows if row["timestamp"] > cutoff)
                duplicate_count = (
                    int(old_meta.get("duplicateRecordCount", 0))
                    + raw_current_count
                    - added_count
                )
            else:
                rows, duplicate_count = merge_exports(
                    sources,
                    closed_history_baseline=(
                        baseline_contribution if explicit_baseline else None
                    ),
                )
    payload = build_payload(
        rows,
        args.guild_name,
        source_files=sources,
        duplicate_count=duplicate_count,
        inventory_audit=inventory_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        CONTRIBUTION_DATA_PREFIX + json.dumps(payload, separators=(",", ":")) + ";\n",
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
    if inventory_audit is not None:
        print(
            "All-goods inventory audit passed: "
            f"{inventory_audit['goodsChecked']} goods across "
            f"{inventory_audit['agesChecked']} ages."
        )


if __name__ == "__main__":
    main()
