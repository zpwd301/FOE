#!/usr/bin/env python3
"""Export Forge Hammer treasury balances and contribution logs through Chrome.

This command does not construct game API requests or choose request IDs. It
launches the configured Chrome profile once with the companion extension in
``chrome/forge-hammer-treasury-exporter``. The companion invokes the game's own
Guild Treasury action exactly once when needed, opens the official contribution
log when needed, and advances each log page exactly once until the configured
overlap is reached. Forge Hammer observes those game-owned requests and exports
both CSV formats. This process watches Downloads, validates each new CSV, and
atomically copies it into the corresponding ``input/`` directory. After both
validated exports are available, it refreshes the treasury dashboard from the
current treasury CSV and the contribution dashboard from all overlapping
contribution CSVs.

The state file is deliberately fail-closed: a failed or interrupted attempt is
not retried automatically on the same date.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode

from generate_contribution_dashboard import REQUIRED_COLUMNS, parse_amount, parse_timestamp
from sync_foe_treasury import DEFAULT_CREDENTIAL_FILE, PROJECT_DIR, SyncError, read_env_file


DEFAULT_CHROME_BINARY = (
    Path(os.sep)
    / "Applications"
    / "Google Chrome.app"
    / "Contents"
    / "MacOS"
    / "Google Chrome"
)
DEFAULT_CHROME_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome"
DEFAULT_CHROME_PROFILE = "Profile 3"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads"
DEFAULT_INPUT_DIR = PROJECT_DIR / "input"
DEFAULT_CONTRIBUTION_INPUT_DIR = DEFAULT_INPUT_DIR / "guild-goods-contribution"
DEFAULT_STATE_FILE = PROJECT_DIR / ".foe-forge-hammer-state.json"
COMPANION_EXTENSION_DIR = PROJECT_DIR / "chrome/forge-hammer-treasury-exporter"
FORGE_HAMMER_EXTENSION_ID = "kmicglnhmpaebfcoiojigbnepklclboa"
TRIGGER_PREFIX = "forge-hammer-treasury-export="
LEGACY_GOODS = 110
EXPECTED_GOODS = 115
DOWNLOAD_RE = re.compile(r"^stats-(\d{4}-\d{2}-\d{2})(?: \(\d+\))?\.csv$")
CONTRIBUTION_DOWNLOAD_RE = re.compile(
    r"^GuildTreasury-(\d{4}-\d{2}-\d{2})(?: \(\d+\))?\.csv$"
)
CONTRIBUTION_PAGE_SIZE = 10
CHROME_CLOSE_TIMEOUT_SECONDS = 15.0


class BrowserExportError(SyncError):
    """A safe failure from the Forge Hammer browser export."""


@dataclass(frozen=True)
class CsvSummary:
    path: Path
    snapshots: int
    goods: int
    last_date: dt.date
    sha256: str


@dataclass(frozen=True)
class ContributionCsvSummary:
    path: Path
    records: int
    newest_timestamp: dt.datetime
    oldest_timestamp: dt.datetime
    final_page_first_timestamp: dt.datetime
    sha256: str


@dataclass(frozen=True)
class BrowserConfig:
    world: str
    chrome_binary: Path
    user_data_dir: Path
    profile_directory: str
    download_dir: Path
    input_dir: Path
    contribution_input_dir: Path
    state_file: Path
    timeout_seconds: float
    world_name: str = "Yorkton"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export Forge Hammer's daily guild treasury and overlapping contribution CSVs "
            "through Chrome, then refresh both dashboards."
        )
    )
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIAL_FILE)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument(
        "--contribution-input-dir",
        type=Path,
        default=DEFAULT_CONTRIBUTION_INPUT_DIR,
    )
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without opening Chrome or writing state.",
    )
    refresh_group = parser.add_mutually_exclusive_group()
    refresh_group.add_argument(
        "--refresh",
        dest="refresh",
        action="store_true",
        help="Refresh both dashboards after importing CSVs (default).",
    )
    refresh_group.add_argument(
        "--no-refresh",
        dest="refresh",
        action="store_false",
        help="Stop after validating and saving the CSV files.",
    )
    refresh_group.add_argument(
        "--rebuild",
        dest="refresh",
        action="store_true",
        help="Deprecated alias for --refresh.",
    )
    parser.set_defaults(refresh=True)
    parser.add_argument(
        "--allow-same-day-retry",
        action="store_true",
        help="Allow one explicitly authorized attempt despite today's recorded state.",
    )
    parser.add_argument(
        "--close-running-profile",
        action="store_true",
        help=(
            "Before exporting, gracefully close only a Chrome process launched with the "
            "configured automation data directory and profile. Unrelated Chrome processes "
            "are never closed."
        ),
    )
    parser.add_argument(
        "--live-debug",
        action="store_true",
        help=(
            "Record a browser-side one-shot trace and leave Chrome open for manual "
            "inspection after completion or failure."
        ),
    )
    return parser.parse_args()


def _setting(values: dict[str, str], name: str, default: str) -> str:
    return os.environ.get(name, values.get(name, default)).strip()


def load_browser_config(args: argparse.Namespace) -> BrowserConfig:
    values = read_env_file(args.credentials)
    world = _setting(values, "FOE_WORLD", "us24").lower()
    if not re.fullmatch(r"[a-z]{2,4}[0-9]+", world):
        raise BrowserExportError("FOE_WORLD must look like us24, en1, or de12.")
    world_name = _setting(
        values,
        "FOE_WORLD_NAME",
        {"us24": "Yorkton"}.get(world, ""),
    )
    if not world_name:
        raise BrowserExportError(
            "FOE_WORLD_NAME is required when the configured world has no known display name."
        )
    try:
        timeout = float(_setting(values, "FOE_FORGE_HAMMER_TIMEOUT_SECONDS", "600"))
    except ValueError as error:
        raise BrowserExportError("FOE_FORGE_HAMMER_TIMEOUT_SECONDS must be numeric.") from error
    if not 30 <= timeout <= 600:
        raise BrowserExportError("FOE_FORGE_HAMMER_TIMEOUT_SECONDS must be between 30 and 600.")

    return BrowserConfig(
        world=world,
        chrome_binary=Path(
            _setting(values, "FOE_CHROME_BINARY", str(DEFAULT_CHROME_BINARY))
        ).expanduser(),
        user_data_dir=Path(
            _setting(values, "FOE_CHROME_USER_DATA_DIR", str(DEFAULT_CHROME_USER_DATA_DIR))
        ).expanduser(),
        profile_directory=_setting(
            values, "FOE_CHROME_PROFILE_DIRECTORY", DEFAULT_CHROME_PROFILE
        ),
        download_dir=Path(
            _setting(values, "FOE_DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR))
        ).expanduser(),
        input_dir=args.input_dir.expanduser().resolve(),
        contribution_input_dir=args.contribution_input_dir.expanduser().resolve(),
        state_file=args.state_file.expanduser().resolve(),
        timeout_seconds=timeout,
        world_name=world_name,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_header(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle, delimiter=";"))
    except (OSError, StopIteration, csv.Error) as error:
        raise BrowserExportError(f"Could not read CSV header from {path}.") from error


def find_reference_header(input_dir: Path, *, exclude: Path | None = None) -> list[str] | None:
    candidates = sorted(
        (
            path
            for path in input_dir.glob("stats-????-??-??.csv")
            if path.is_file() and (exclude is None or path.resolve() != exclude.resolve())
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for path in candidates:
        try:
            header = read_csv_header(path)
        except BrowserExportError:
            continue
        if (
            header
            and header[0] == "DateTime"
            and len(header) - 1 in {LEGACY_GOODS, EXPECTED_GOODS}
        ):
            return header
    return None


def treasury_headers_compatible(first: Sequence[str], second: Sequence[str]) -> bool:
    """Accept only the known one-age migration, with five columns appended."""
    if list(first) == list(second):
        return True
    shorter, longer = sorted((list(first), list(second)), key=len)
    return (
        len(shorter) == LEGACY_GOODS + 1
        and len(longer) == EXPECTED_GOODS + 1
        and longer[: len(shorter)] == shorter
    )


def validate_treasury_csv(
    path: Path,
    *,
    expected_date: dt.date,
    expected_header: Sequence[str] | None = None,
    allow_legacy_goods: bool = False,
) -> CsvSummary:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
    except (OSError, csv.Error) as error:
        raise BrowserExportError(f"Could not read treasury export {path}.") from error

    if len(rows) < 2:
        raise BrowserExportError("Treasury export does not contain any snapshots.")
    header = rows[0]
    if not header or header[0] != "DateTime":
        raise BrowserExportError("Treasury export is missing the DateTime header.")
    goods_count = len(header) - 1
    allowed_goods = {EXPECTED_GOODS}
    if allow_legacy_goods:
        allowed_goods.add(LEGACY_GOODS)
    if goods_count not in allowed_goods:
        expected = " or ".join(str(count) for count in sorted(allowed_goods))
        raise BrowserExportError(
            f"Treasury export has {goods_count} goods; expected {expected}."
        )
    if len(set(header)) != len(header):
        raise BrowserExportError("Treasury export contains duplicate columns.")
    if expected_header is not None and not treasury_headers_compatible(expected_header, header):
        raise BrowserExportError(
            "Treasury export goods columns are not an exact match or the supported "
            "five-column age extension; manual review required."
        )

    seen_dates: set[dt.datetime] = set()
    seen_calendar_dates: set[dt.date] = set()
    parsed_dates: list[dt.datetime] = []
    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise BrowserExportError(
                f"Treasury export row {line_number} has {len(row)} columns; expected {len(header)}."
            )
        try:
            timestamp = dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except ValueError as error:
            raise BrowserExportError(
                f"Treasury export row {line_number} has an invalid DateTime."
            ) from error
        if timestamp in seen_dates:
            raise BrowserExportError("Treasury export contains duplicate snapshot dates.")
        if timestamp.date() in seen_calendar_dates:
            raise BrowserExportError("Treasury export contains multiple snapshots for one date.")
        seen_dates.add(timestamp)
        seen_calendar_dates.add(timestamp.date())
        parsed_dates.append(timestamp)
        for value in row[1:]:
            try:
                amount = int(value)
            except ValueError as error:
                raise BrowserExportError(
                    f"Treasury export row {line_number} contains a non-numeric amount."
                ) from error
            if amount < 0:
                raise BrowserExportError("Treasury export contains a negative amount.")

    if parsed_dates != sorted(parsed_dates):
        raise BrowserExportError("Treasury snapshots are not sorted chronologically.")
    last_date = parsed_dates[-1].date()
    if last_date != expected_date:
        raise BrowserExportError(
            f"Treasury export ends on {last_date.isoformat()}, not {expected_date.isoformat()}."
        )
    return CsvSummary(
        path=path,
        snapshots=len(rows) - 1,
        goods=len(header) - 1,
        last_date=last_date,
        sha256=_sha256(path),
    )


def find_treasury_history_reference(
    input_dir: Path,
    *,
    expected_header: Sequence[str],
    exclude: Path | None = None,
) -> tuple[Path, CsvSummary] | None:
    """Select the longest compatible prior export, not merely the newest file."""
    candidates: list[tuple[int, dt.date, int, str, Path, CsvSummary]] = []
    for path in input_dir.glob("stats-????-??-??.csv"):
        if not path.is_file() or (exclude is not None and path.resolve() == exclude.resolve()):
            continue
        match = DOWNLOAD_RE.fullmatch(path.name)
        if not match:
            continue
        try:
            export_date = dt.date.fromisoformat(match.group(1))
            summary = validate_treasury_csv(
                path,
                expected_date=export_date,
                expected_header=expected_header,
                allow_legacy_goods=True,
            )
        except (ValueError, BrowserExportError):
            continue
        candidates.append(
            (
                summary.snapshots,
                summary.last_date,
                path.stat().st_mtime_ns,
                path.name,
                path,
                summary,
            )
        )
    if not candidates:
        return None
    *_, path, summary = max(candidates)
    return path, summary


def _read_treasury_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
    except (OSError, csv.Error) as error:
        raise BrowserExportError(f"Could not read treasury export {path}.") from error
    if not rows:
        raise BrowserExportError(f"Treasury export {path} is empty.")
    return rows[0], rows[1:]


def _write_treasury_rows(
    path: Path,
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(
                handle,
                delimiter=";",
                lineterminator="\n",
                quoting=csv.QUOTE_NONNUMERIC,
            )
            writer.writerow(header)
            for row in rows:
                writer.writerow([row[0], *(int(value) for value in row[1:])])
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _expand_legacy_treasury_rows(
    source_header: Sequence[str],
    rows: Sequence[Sequence[str]],
    target_header: Sequence[str],
) -> list[list[str]]:
    if list(source_header) == list(target_header):
        return [list(row) for row in rows]
    if not treasury_headers_compatible(source_header, target_header):
        raise BrowserExportError(
            "Treasury history columns differ from the downloaded export; no data was replaced."
        )
    if len(source_header) >= len(target_header):
        raise BrowserExportError(
            "Treasury history cannot replace a newer goods schema; no data was replaced."
        )
    missing_values = len(target_header) - len(source_header)
    return [list(row) + ["0"] * missing_values for row in rows]


def merge_treasury_csv_history(
    downloaded: Path,
    destination: Path,
    *,
    input_dir: Path,
    expected_date: dt.date,
    expected_header: Sequence[str] | None = None,
) -> tuple[CsvSummary, CsvSummary, tuple[Path, CsvSummary] | None]:
    """Merge a profile-local Forge Hammer export with the longest saved history."""
    downloaded_summary = validate_treasury_csv(
        downloaded,
        expected_date=expected_date,
        expected_header=expected_header,
    )
    header, downloaded_rows = _read_treasury_rows(downloaded)
    reference = find_treasury_history_reference(
        input_dir,
        expected_header=header,
        exclude=destination,
    )

    rows_by_date: dict[dt.date, list[str]] = {}
    if reference is not None:
        reference_path, _ = reference
        reference_header, reference_rows = _read_treasury_rows(reference_path)
        reference_rows = _expand_legacy_treasury_rows(
            reference_header,
            reference_rows,
            header,
        )
        for row in reference_rows:
            rows_by_date[dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").date()] = row

    # The current download is authoritative for any date it contains, while all
    # older dates absent from a fresh Chrome profile remain preserved.
    for row in downloaded_rows:
        rows_by_date[dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").date()] = row
    merged_rows = [rows_by_date[date] for date in sorted(rows_by_date)]
    staged = destination.with_name(f".{destination.name}.{os.getpid()}.merge")
    try:
        _write_treasury_rows(staged, header, merged_rows)
        staged_summary = validate_treasury_csv(
            staged,
            expected_date=expected_date,
            expected_header=header,
        )
        if reference is not None:
            _, reference_summary = reference
            expected_minimum = reference_summary.snapshots + int(
                expected_date > reference_summary.last_date
            )
            if staged_summary.snapshots < expected_minimum:
                raise BrowserExportError(
                    "Treasury history merge lost prior snapshots; no dashboard refresh was attempted."
                )
        os.replace(staged, destination)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    merged_summary = validate_treasury_csv(
        destination,
        expected_date=expected_date,
        expected_header=header,
    )
    return merged_summary, downloaded_summary, reference


def contribution_export_files(
    input_dir: Path,
    *,
    exclude: Path | None = None,
) -> list[Path]:
    candidates: list[tuple[dt.date, int, str, Path]] = []
    for path in input_dir.glob("GuildTreasury-????-??-??.csv"):
        if not path.is_file() or (exclude is not None and path.resolve() == exclude.resolve()):
            continue
        match = CONTRIBUTION_DOWNLOAD_RE.fullmatch(path.name)
        if not match:
            continue
        try:
            export_date = dt.date.fromisoformat(match.group(1))
        except ValueError:
            continue
        candidates.append((export_date, path.stat().st_mtime_ns, path.name, path))
    return [item[-1] for item in sorted(candidates)]


def newest_contribution_timestamp(path: Path) -> dt.datetime:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if list(reader.fieldnames or []) != list(REQUIRED_COLUMNS):
                raise BrowserExportError(
                    f"Contribution reference {path} has an unexpected header."
                )
            timestamps = [parse_timestamp(row["Date/Time"] or "") for row in reader]
    except (OSError, csv.Error, ValueError) as error:
        if isinstance(error, BrowserExportError):
            raise
        raise BrowserExportError(
            f"Could not read contribution timestamps from {path}."
        ) from error
    if not timestamps:
        raise BrowserExportError(f"Contribution reference {path} contains no records.")
    return max(timestamps)


def find_contribution_cutoff(
    input_dir: Path,
    *,
    exclude: Path | None = None,
) -> tuple[Path, dt.datetime, dt.datetime]:
    candidates = contribution_export_files(input_dir, exclude=exclude)
    if not candidates:
        raise BrowserExportError(
            "No prior GuildTreasury CSV exists to establish the contribution overlap cutoff."
        )
    reference = candidates[-1]
    newest = newest_contribution_timestamp(reference)
    return reference, newest, newest - dt.timedelta(hours=1)


def validate_contribution_csv(
    path: Path,
    *,
    cutoff: dt.datetime,
) -> ContributionCsvSummary:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
    except (OSError, csv.Error) as error:
        raise BrowserExportError(f"Could not read contribution export {path}.") from error

    if len(rows) < 2:
        raise BrowserExportError("Contribution export does not contain any records.")
    header = rows[0]
    if header != list(REQUIRED_COLUMNS):
        raise BrowserExportError("Contribution export has an unexpected column schema.")

    timestamps: list[dt.datetime] = []
    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(header):
            raise BrowserExportError(
                f"Contribution export row {line_number} has {len(row)} columns; "
                f"expected {len(header)}."
            )
        try:
            parse_amount(row[4])
            timestamp = parse_timestamp(row[6])
        except ValueError as error:
            raise BrowserExportError(
                f"Contribution export row {line_number} is invalid: {error}"
            ) from error
        timestamps.append(timestamp)

    final_page_start = ((len(timestamps) - 1) // CONTRIBUTION_PAGE_SIZE) * CONTRIBUTION_PAGE_SIZE
    final_page_first_timestamp = timestamps[final_page_start]
    # The companion enforces the cutoff while it still has another server page.
    # A server-exhausted export can legitimately end on an exactly full page,
    # and Forge Hammer's CSV does not include the response's total-count field.

    return ContributionCsvSummary(
        path=path,
        records=len(timestamps),
        newest_timestamp=max(timestamps),
        oldest_timestamp=min(timestamps),
        final_page_first_timestamp=final_page_first_timestamp,
        sha256=_sha256(path),
    )


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise BrowserExportError("Forge Hammer state path must not be a symbolic link.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BrowserExportError("Forge Hammer state file is invalid.") from error
    if not isinstance(payload, dict):
        raise BrowserExportError("Forge Hammer state file has an unexpected shape.")
    return payload


def ensure_attempt_allowed(
    state_file: Path,
    sync_date: dt.date,
    *,
    allow_same_day_retry: bool = False,
) -> None:
    state = _read_state(state_file)
    if not state or state.get("date") != sync_date.isoformat():
        return
    status = state.get("status")
    if status in {"started", "failed", "success"}:
        if allow_same_day_retry:
            return
        raise BrowserExportError(
            "A Forge Hammer export was already attempted today. Refusing an automatic retry; "
            "review the state file before any manual retry."
        )


def find_forge_hammer_manifest(config: BrowserConfig) -> Path:
    extension_root = (
        config.user_data_dir
        / config.profile_directory
        / "Extensions"
        / FORGE_HAMMER_EXTENSION_ID
    )
    manifests = sorted(extension_root.glob("*/manifest.json"), reverse=True)
    if not manifests:
        raise BrowserExportError(
            f"Forge Hammer is not installed in Chrome profile {config.profile_directory!r}."
        )
    return manifests[0]


def running_chrome_processes(chrome_binary: Path) -> tuple[tuple[int, str], ...]:
    if sys.platform != "darwin":
        return ()
    result = subprocess.run(
        ["pgrep", "-lf", str(chrome_binary)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return ()

    processes: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        pid_text, separator, command = line.strip().partition(" ")
        if not separator:
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        processes.append((pid, command))
    return tuple(processes)


def chrome_data_dir_is_running(
    processes: Sequence[tuple[int, str]],
    user_data_dir: Path,
) -> bool:
    if not processes:
        return False

    configured_data_dir = user_data_dir.expanduser().resolve(strict=False)
    default_data_dir = DEFAULT_CHROME_USER_DATA_DIR.expanduser().resolve(strict=False)
    if configured_data_dir == default_data_dir:
        # Chrome omits --user-data-dir when it uses its normal data directory,
        # so any running instance can hold the configured profile lock.
        return True

    marker = f"--user-data-dir={configured_data_dir}"
    return any(marker in command for _, command in processes)


def chrome_is_running(chrome_binary: Path, user_data_dir: Path) -> bool:
    return chrome_data_dir_is_running(
        running_chrome_processes(chrome_binary),
        user_data_dir,
    )


def close_running_chrome_profile(config: BrowserConfig) -> bool:
    processes = running_chrome_processes(config.chrome_binary)
    if not chrome_data_dir_is_running(processes, config.user_data_dir):
        return False

    chrome_binary = str(config.chrome_binary)
    configured_data_dir = config.user_data_dir.expanduser().resolve(strict=False)
    data_dir_marker = f"--user-data-dir={configured_data_dir}"
    profile_marker = f"--profile-directory={config.profile_directory}"
    matching_pids = tuple(
        pid
        for pid, command in processes
        if (command == chrome_binary or command.startswith(f"{chrome_binary} "))
        and data_dir_marker in command
        and profile_marker in command
    )
    if not matching_pids:
        raise BrowserExportError(
            "The configured Chrome data directory is in use, but no Chrome process "
            f"launched for {config.profile_directory!r} was found. Refusing to close "
            "a Chrome process that does not match the configured profile."
        )

    print(f"Closing the running Chrome automation instance for {config.profile_directory!r}.")
    for pid in matching_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError as error:
            raise BrowserExportError(
                f"Could not close Chrome process {pid} for {config.profile_directory!r}."
            ) from error

    deadline = time.monotonic() + CHROME_CLOSE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        remaining = {pid for pid, _ in running_chrome_processes(config.chrome_binary)}
        if not remaining.intersection(matching_pids):
            break
        time.sleep(0.25)
    else:
        raise BrowserExportError(
            f"Chrome did not close {config.profile_directory!r} within "
            f"{CHROME_CLOSE_TIMEOUT_SECONDS:g} seconds."
        )

    if chrome_is_running(config.chrome_binary, config.user_data_dir):
        raise BrowserExportError(
            f"Chrome closed the automation process for {config.profile_directory!r}, but "
            "the shared data directory is still in use by another Chrome process. "
            "Refusing to close a process that does not match the configured profile."
        )
    print(f"Chrome automation instance for {config.profile_directory!r} closed.")
    return True


def preflight(config: BrowserConfig, *, require_stopped_chrome: bool = True) -> Path:
    if sys.platform != "darwin":
        raise BrowserExportError("The Forge Hammer Chrome launcher currently supports macOS only.")
    if not config.chrome_binary.is_file():
        raise BrowserExportError(f"Google Chrome was not found at {config.chrome_binary}.")
    profile_path = config.user_data_dir / config.profile_directory
    if not profile_path.is_dir():
        raise BrowserExportError(f"Chrome profile was not found: {profile_path}.")
    manifest = find_forge_hammer_manifest(config)
    if not (COMPANION_EXTENSION_DIR / "manifest.json").is_file():
        raise BrowserExportError("The Forge Hammer companion extension is missing.")
    if not config.download_dir.is_dir():
        raise BrowserExportError(f"Download directory was not found: {config.download_dir}.")
    if not config.contribution_input_dir.is_dir():
        raise BrowserExportError(
            f"Contribution input directory was not found: {config.contribution_input_dir}."
        )
    if require_stopped_chrome and chrome_is_running(
        config.chrome_binary,
        config.user_data_dir,
    ):
        raise BrowserExportError(
            "The configured Chrome automation data directory is already in use. Close that "
            f"Chrome instance so the script can start {config.profile_directory!r} with the "
            "installed companion extension; no browser was opened."
        )
    return manifest


def _download_snapshot(
    download_dir: Path,
    *,
    filename_glob: str,
    filename_re: re.Pattern[str],
) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in download_dir.glob(filename_glob):
        if filename_re.fullmatch(path.name):
            stat_result = path.stat()
            snapshot[path] = (stat_result.st_mtime_ns, stat_result.st_size)
    return snapshot


def wait_for_download(
    download_dir: Path,
    *,
    sync_date: dt.date,
    baseline: dict[Path, tuple[int, int]],
    started_ns: int,
    timeout_seconds: float,
    filename_prefix: str = "stats-",
    filename_re: re.Pattern[str] = DOWNLOAD_RE,
    export_label: str = "treasury",
) -> Path:
    deadline = time.monotonic() + timeout_seconds
    date_text = sync_date.isoformat()
    previous: tuple[Path, int, int] | None = None
    stable_polls = 0
    while time.monotonic() < deadline:
        candidates: list[tuple[int, Path, int]] = []
        for path in download_dir.glob(f"{filename_prefix}{date_text}*.csv"):
            if not filename_re.fullmatch(path.name):
                continue
            stat_result = path.stat()
            signature = (stat_result.st_mtime_ns, stat_result.st_size)
            if stat_result.st_mtime_ns < started_ns or baseline.get(path) == signature:
                continue
            candidates.append((stat_result.st_mtime_ns, path, stat_result.st_size))
        if candidates:
            modified_ns, path, size = max(candidates)
            current = (path, modified_ns, size)
            if current == previous and size > 0:
                stable_polls += 1
            else:
                previous = current
                stable_polls = 0
            if stable_polls >= 2:
                return path
        time.sleep(0.5)
    raise BrowserExportError(
        f"Forge Hammer did not produce a new {export_label} CSV before the timeout. "
        "No retry was attempted; inspect Chrome and the state file."
    )


def launch_chrome(
    config: BrowserConfig,
    nonce: str,
    *,
    export_treasury: bool,
    export_contributions: bool,
    contribution_cutoff: dt.datetime | None,
    live_debug: bool = False,
) -> subprocess.Popen[bytes]:
    trigger_params = {
        TRIGGER_PREFIX.removesuffix("="): nonce,
        "treasury": "1" if export_treasury else "0",
        "contributions": "1" if export_contributions else "0",
        "world_name": config.world_name,
    }
    if live_debug:
        trigger_params["live_debug"] = "1"
    if contribution_cutoff is not None:
        trigger_params["contribution_cutoff"] = contribution_cutoff.isoformat(timespec="seconds")
    game_url = (
        f"https://{config.world}.forgeofempires.com/game/index?#{urlencode(trigger_params)}"
    )
    command = [
        str(config.chrome_binary),
        f"--user-data-dir={config.user_data_dir}",
        f"--profile-directory={config.profile_directory}",
        "--new-window",
        game_url,
    ]
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def import_export(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    shutil.copyfile(source, temporary)
    os.chmod(temporary, 0o644)
    os.replace(temporary, destination)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        return str(path)


def rebuild_treasury_dashboard(csv_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(PROJECT_DIR / "generate_treasury_dashboard.py"),
            "--csv",
            str(csv_path),
        ],
        cwd=PROJECT_DIR,
        check=True,
    )


def rebuild_contribution_dashboard(input_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(PROJECT_DIR / "generate_contribution_dashboard.py"),
            "--input-dir",
            str(input_dir),
        ],
        cwd=PROJECT_DIR,
        check=True,
    )


def main() -> int:
    args = parse_args()
    try:
        config = load_browser_config(args)
        sync_date = dt.datetime.now().astimezone().date()
        date_text = sync_date.isoformat()
        treasury_destination = config.input_dir / f"stats-{date_text}.csv"
        contribution_destination = (
            config.contribution_input_dir / f"GuildTreasury-{date_text}.csv"
        )
        reference_header = find_reference_header(
            config.input_dir,
            exclude=treasury_destination,
        )
        contribution_reference, contribution_reference_timestamp, contribution_cutoff = (
            find_contribution_cutoff(
                config.contribution_input_dir,
                exclude=contribution_destination,
            )
        )

        treasury_summary: CsvSummary | None = None
        contribution_summary: ContributionCsvSummary | None = None
        if treasury_destination.is_file():
            treasury_summary = validate_treasury_csv(
                treasury_destination,
                expected_date=sync_date,
                expected_header=reference_header,
            )
            print(
                f"Treasury export already present: {treasury_destination} "
                f"({treasury_summary.snapshots} snapshots, {treasury_summary.goods} goods)."
            )

        if contribution_destination.is_file():
            contribution_summary = validate_contribution_csv(
                contribution_destination,
                cutoff=contribution_cutoff,
            )
            print(
                f"Contribution export already present: {contribution_destination} "
                f"({contribution_summary.records} records)."
            )

        export_treasury = treasury_summary is None
        export_contributions = contribution_summary is None
        if not export_treasury and not export_contributions:
            print("Both validated exports are present. No browser opened.")
            if args.dry_run:
                print(
                    "Dry run only; would refresh both dashboards from the validated "
                    "treasury file and all contribution CSVs."
                )
            elif args.refresh:
                rebuild_contribution_dashboard(config.contribution_input_dir)
                rebuild_treasury_dashboard(treasury_destination)
                print("Treasury and contribution dashboards rebuilt.")
            return 0

        if not args.dry_run and args.close_running_profile:
            close_running_chrome_profile(config)
        manifest = preflight(config, require_stopped_chrome=not args.dry_run)
        previous_state = _read_state(config.state_file)
        ensure_attempt_allowed(
            config.state_file,
            sync_date,
            allow_same_day_retry=args.allow_same_day_retry,
        )
        if args.dry_run:
            requested = ", ".join(
                label
                for label, enabled in (
                    ("treasury", export_treasury),
                    ("contributions", export_contributions),
                )
                if enabled
            )
            print(
                f"Preflight passed for {config.profile_directory}; "
                f"Forge Hammer manifest: {manifest}. Would export: {requested}. "
                f"Contribution cutoff: {contribution_cutoff.isoformat(sep=' ')} from "
                f"{contribution_reference.name}. No browser opened."
            )
            return 0

        treasury_baseline = _download_snapshot(
            config.download_dir,
            filename_glob="stats-*.csv",
            filename_re=DOWNLOAD_RE,
        )
        contribution_baseline = _download_snapshot(
            config.download_dir,
            filename_glob="GuildTreasury-*.csv",
            filename_re=CONTRIBUTION_DOWNLOAD_RE,
        )
        nonce = uuid.uuid4().hex
        started_at = dt.datetime.now(dt.timezone.utc)
        started_ns = time.time_ns()
        state: dict[str, Any] = {
            "schema_version": 2,
            "date": sync_date.isoformat(),
            "status": "started",
            "started_at": started_at.isoformat(),
            "world": config.world,
            "world_name": config.world_name,
            "profile_directory": config.profile_directory,
            "nonce_fingerprint": hashlib.sha256(nonce.encode()).hexdigest()[:16],
            "requested_exports": {
                "treasury": export_treasury,
                "contributions": export_contributions,
            },
            "live_debug": args.live_debug,
            "contribution_reference": display_path(contribution_reference),
            "contribution_reference_timestamp": contribution_reference_timestamp.isoformat(),
            "contribution_cutoff": contribution_cutoff.isoformat(),
        }
        if (
            args.allow_same_day_retry
            and previous_state
            and previous_state.get("date") == sync_date.isoformat()
        ):
            state["same_day_retry_authorized"] = True
            state["previous_attempt"] = previous_state
        _write_state(config.state_file, state)
        launch_chrome(
            config,
            nonce,
            export_treasury=export_treasury,
            export_contributions=export_contributions,
            contribution_cutoff=contribution_cutoff if export_contributions else None,
            live_debug=args.live_debug,
        )
        requested_description = " and ".join(
            label
            for label, enabled in (
                ("treasury", export_treasury),
                ("contribution logs", export_contributions),
            )
            if enabled
        )
        print(
            f"Chrome started with {config.profile_directory}; the game will request "
            f"{requested_description} through its official UI, with no request retries."
        )
        if args.live_debug:
            print(
                "Live diagnostic tracing is enabled; Chrome will remain open for manual "
                "inspection after the run."
            )

        treasury_downloaded: Path | None = None
        contribution_downloaded: Path | None = None
        try:
            if export_treasury:
                treasury_downloaded = wait_for_download(
                    config.download_dir,
                    sync_date=sync_date,
                    baseline=treasury_baseline,
                    started_ns=started_ns,
                    timeout_seconds=config.timeout_seconds,
                )
                (
                    treasury_summary,
                    downloaded_treasury_summary,
                    treasury_history_reference,
                ) = merge_treasury_csv_history(
                    treasury_downloaded,
                    treasury_destination,
                    input_dir=config.input_dir,
                    expected_date=sync_date,
                    expected_header=reference_header,
                )

            if export_contributions:
                contribution_downloaded = wait_for_download(
                    config.download_dir,
                    sync_date=sync_date,
                    baseline=contribution_baseline,
                    started_ns=started_ns,
                    timeout_seconds=config.timeout_seconds,
                    filename_prefix="GuildTreasury-",
                    filename_re=CONTRIBUTION_DOWNLOAD_RE,
                    export_label="contribution",
                )
                downloaded_contribution_summary = validate_contribution_csv(
                    contribution_downloaded,
                    cutoff=contribution_cutoff,
                )
                import_export(contribution_downloaded, contribution_destination)
                contribution_summary = validate_contribution_csv(
                    contribution_destination,
                    cutoff=contribution_cutoff,
                )
                if contribution_summary.sha256 != downloaded_contribution_summary.sha256:
                    raise BrowserExportError(
                        "Imported contribution CSV does not match the download."
                    )

            if treasury_summary is None or contribution_summary is None:
                raise BrowserExportError("A requested Forge Hammer export did not complete.")

            if args.refresh:
                rebuild_contribution_dashboard(config.contribution_input_dir)
                rebuild_treasury_dashboard(treasury_destination)
        except BaseException as error:
            state.update(
                status="failed",
                completed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                failure_type=type(error).__name__,
                failure_message=str(error)[:500],
            )
            _write_state(config.state_file, state)
            raise

        state.update(
            status="success",
            completed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            treasury={
                "download_name": treasury_downloaded.name if treasury_downloaded else None,
                "download_snapshots": (
                    downloaded_treasury_summary.snapshots if treasury_downloaded else None
                ),
                "history_reference": (
                    display_path(treasury_history_reference[0])
                    if treasury_downloaded and treasury_history_reference
                    else None
                ),
                "output": display_path(treasury_destination),
                "snapshots": treasury_summary.snapshots,
                "goods": treasury_summary.goods,
                "sha256": treasury_summary.sha256,
            },
            contributions={
                "download_name": (
                    contribution_downloaded.name if contribution_downloaded else None
                ),
                "output": display_path(contribution_destination),
                "records": contribution_summary.records,
                "newest_timestamp": contribution_summary.newest_timestamp.isoformat(),
                "oldest_timestamp": contribution_summary.oldest_timestamp.isoformat(),
                "final_page_first_timestamp": (
                    contribution_summary.final_page_first_timestamp.isoformat()
                ),
                "sha256": contribution_summary.sha256,
            },
            dashboards_refreshed=args.refresh,
        )
        _write_state(config.state_file, state)
        print(
            f"Treasury: {display_path(treasury_destination)} "
            f"({treasury_summary.snapshots} snapshots, {treasury_summary.goods} goods)."
        )
        print(
            f"Contributions: {display_path(contribution_destination)} "
            f"({contribution_summary.records} records, "
            f"{contribution_summary.newest_timestamp.isoformat(sep=' ')} through "
            f"{contribution_summary.oldest_timestamp.isoformat(sep=' ')})."
        )
        if args.refresh:
            print("Treasury and contribution dashboards rebuilt.")
        return 0
    except (BrowserExportError, SyncError) as error:
        print(f"Forge Hammer export failed: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"Forge Hammer export failed while rebuilding: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
