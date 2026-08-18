#!/usr/bin/env python3
"""Run one fail-closed daily Forge Hammer refresh and optionally publish it."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence


DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[1]
ALLOWED_EXACT_PATHS = {
    "site/data/contribution-data.js",
    "site/data/treasury-data.js",
}
ALLOWED_PREFIXES = ("dashboard/",)
TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]*-[1-9][0-9]*$")


class AutomationError(RuntimeError):
    """A safe failure that must not trigger another game attempt."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one treasury and contribution export, validate the dashboard, and "
            "optionally publish generated data. No failed game action is retried."
        )
    )
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--ticket", default="FOE-30")
    return parser.parse_args()


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def git_output(project_dir: Path, *arguments: str) -> str:
    return run(
        ["git", *arguments],
        cwd=project_dir,
        capture_output=True,
    ).stdout.strip()


def normalized_git_paths(project_dir: Path, output: str) -> set[str]:
    prefix = git_output(project_dir, "rev-parse", "--show-prefix")
    return {
        line[len(prefix) :] if prefix and line.startswith(prefix) else line
        for raw_line in output.splitlines()
        if (line := raw_line.strip())
    }


def project_changes(project_dir: Path) -> set[str]:
    tracked = git_output(project_dir, "diff", "--name-only", "HEAD", "--", ".")
    untracked = git_output(
        project_dir,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        ".",
    )
    return normalized_git_paths(project_dir, tracked) | normalized_git_paths(
        project_dir,
        untracked,
    )


def is_allowed_generated_path(path: str) -> bool:
    return path in ALLOWED_EXACT_PATHS or path.startswith(ALLOWED_PREFIXES)


def ensure_clean_start(project_dir: Path) -> None:
    staged = run(
        ["git", "diff", "--cached", "--quiet", "--", "."],
        cwd=project_dir,
        check=False,
    )
    if staged.returncode != 0:
        raise AutomationError(
            "The project contains staged changes. No export or publish was attempted."
        )
    changes = project_changes(project_dir)
    if changes:
        listing = ", ".join(sorted(changes)[:8])
        raise AutomationError(
            "The project worktree is not clean. Preserve or commit the changes before the "
            f"scheduled refresh. Detected: {listing}"
        )


def ensure_remote_is_current(project_dir: Path, remote: str, branch: str) -> None:
    current_branch = git_output(project_dir, "branch", "--show-current")
    if current_branch != branch:
        raise AutomationError(
            f"Expected branch {branch!r}, found {current_branch!r}; no export was attempted."
        )
    run(
        [
            "git",
            "fetch",
            "--quiet",
            remote,
            f"{branch}:refs/remotes/{remote}/{branch}",
        ],
        cwd=project_dir,
    )
    head = git_output(project_dir, "rev-parse", "HEAD")
    remote_head = git_output(project_dir, "rev-parse", f"{remote}/{branch}")
    if head != remote_head:
        raise AutomationError(
            "The local and remote branches differ. Update or publish the branch manually; "
            "no game request was attempted."
        )


def read_assignment(path: Path, variable: str) -> dict[str, object]:
    prefix = f"window.{variable} = "
    text = path.read_text(encoding="utf-8")
    if not text.startswith(prefix) or not text.rstrip().endswith(";"):
        raise AutomationError(f"{path.name} has an unexpected JavaScript assignment.")
    payload = json.loads(text[len(prefix) :].strip().removesuffix(";"))
    if not isinstance(payload, dict):
        raise AutomationError(f"{path.name} does not contain an object payload.")
    return payload


def treasury_snapshot_dates(project_dir: Path) -> tuple[dt.date, ...]:
    treasury = read_assignment(
        project_dir / "site/data/treasury-data.js",
        "TREASURY_DATA",
    )
    meta = treasury.get("meta")
    raw_dates = treasury.get("dates")
    goods = treasury.get("goods")
    if not isinstance(meta, dict) or not isinstance(raw_dates, list) or not raw_dates:
        raise AutomationError("Generated treasury history metadata is missing.")
    if not isinstance(goods, list):
        raise AutomationError("Generated treasury goods are missing.")
    try:
        dates = tuple(dt.date.fromisoformat(str(value)) for value in raw_dates)
        first_date = dt.date.fromisoformat(str(meta["firstDate"]))
        latest_date = dt.date.fromisoformat(str(meta["latestDate"]))
        snapshot_count = int(meta["availableDays"])
    except (KeyError, TypeError, ValueError) as error:
        raise AutomationError("Generated treasury history metadata is invalid.") from error
    if dates != tuple(sorted(set(dates))):
        raise AutomationError("Generated treasury snapshot dates are not unique and ordered.")
    if first_date != dates[0] or latest_date != dates[-1] or snapshot_count != len(dates):
        raise AutomationError("Generated treasury history metadata is inconsistent.")
    for good in goods:
        if not isinstance(good, dict) or not isinstance(good.get("values"), list):
            raise AutomationError("Generated treasury good history is invalid.")
        if len(good["values"]) != len(dates):
            raise AutomationError("Generated treasury good history lost snapshot values.")
    return dates


def ensure_treasury_history_preserved(
    previous_dates: Sequence[dt.date],
    current_dates: Sequence[dt.date],
) -> None:
    missing = sorted(set(previous_dates) - set(current_dates))
    if missing or len(current_dates) < len(previous_dates):
        detail = ", ".join(date.isoformat() for date in missing[:5])
        raise AutomationError(
            "Treasury history regressed; refusing to publish. Missing prior snapshot dates: "
            + (detail or "unknown")
        )


def validate_generated_metadata(project_dir: Path) -> tuple[dt.date, dt.date]:
    treasury_dates = treasury_snapshot_dates(project_dir)
    contribution = read_assignment(
        project_dir / "site/data/contribution-data.js",
        "CONTRIBUTION_DATA",
    )
    contribution_meta = contribution.get("meta")
    if not isinstance(contribution_meta, dict):
        raise AutomationError("Generated dashboard metadata is missing.")

    try:
        treasury_date = treasury_dates[-1]
        contribution_date = dt.datetime.fromisoformat(
            str(contribution_meta["latestTimestamp"])
        ).date()
        source_count = int(contribution_meta["sourceFileCount"])
        duplicate_count = int(contribution_meta["duplicateRecordCount"])
    except (KeyError, TypeError, ValueError) as error:
        raise AutomationError("Generated dashboard metadata is invalid.") from error

    source_files = contribution_meta.get("sourceFiles")
    if not isinstance(source_files, list) or source_count != len(source_files):
        raise AutomationError("Contribution source-file metadata is inconsistent.")
    expected_sources = sorted(
        path.name
        for path in (project_dir / "input/guild-goods-contribution").glob(
            "GuildTreasury-*.csv"
        )
    )
    if sorted(str(name) for name in source_files) != expected_sources:
        raise AutomationError(
            "Contribution dashboard did not merge every available contribution CSV."
        )
    if duplicate_count < 0:
        raise AutomationError("Contribution duplicate count cannot be negative.")
    return treasury_date, contribution_date


def validate_compatibility_page(project_dir: Path) -> None:
    page = project_dir / "dashboard/treasury/contributions/index.html"
    redirect = project_dir / "dashboard/contributions/index.html"
    if not page.is_file():
        raise AutomationError("The generated contribution dashboard page is missing.")
    redirect_text = redirect.read_text(encoding="utf-8")
    if "/treasury/contributions/" not in redirect_text:
        raise AutomationError("The legacy contribution page no longer points to the dashboard.")


def run_offline_validation(project_dir: Path) -> None:
    node = shutil.which("node")
    if not node:
        raise AutomationError("Node.js is required for dashboard validation.")
    run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=project_dir,
    )
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "py_compile",
            "export_forge_hammer_treasury.py",
            "sync_foe_treasury.py",
        ],
        cwd=project_dir,
    )
    for script in (
        "site/assets/app.js",
        "site/assets/contributions.js",
        "site/data/treasury-data.js",
        "site/data/contribution-data.js",
    ):
        run([node, "--check", script], cwd=project_dir)
    run(["git", "diff", "--check"], cwd=project_dir)
    validate_generated_metadata(project_dir)
    validate_compatibility_page(project_dir)


def ensure_only_generated_changes(project_dir: Path) -> set[str]:
    changes = project_changes(project_dir)
    unexpected = sorted(path for path in changes if not is_allowed_generated_path(path))
    if unexpected:
        raise AutomationError(
            "The export changed files outside the generated dashboard allowlist: "
            + ", ".join(unexpected[:8])
        )
    return changes


def ensure_privacy(project_dir: Path, paths: set[str]) -> None:
    home_path = str(Path.home())
    user_path_re = re.compile(r"/(?:Users|home)/[^/\s\"']+/")
    for relative in sorted(paths):
        path = project_dir / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if home_path in text or user_path_re.search(text):
            raise AutomationError(
                f"Privacy validation found a personal absolute path in {relative}."
            )


def display_date(value: dt.date) -> str:
    return f"{value.strftime('%B')} {value.day}"


def publish_generated_changes(
    project_dir: Path,
    *,
    paths: set[str],
    ticket: str,
    remote: str,
    branch: str,
    through_date: dt.date,
) -> str | None:
    if not paths:
        print("Generated dashboard data is already current; no commit created.")
        return None
    if not TICKET_RE.fullmatch(ticket):
        raise AutomationError("The publishing ticket must use the Jira form KEY-123.")

    hook_path = Path(git_output(project_dir, "rev-parse", "--git-path", "hooks/pre-push"))
    if not hook_path.is_absolute():
        hook_path = project_dir / hook_path
    if not hook_path.is_file() or not os.access(hook_path, os.X_OK):
        raise AutomationError(
            "The repository privacy pre-push hook is not installed; refusing to publish."
        )

    ensure_privacy(project_dir, paths)
    run(
        [
            "git",
            "add",
            "-A",
            "--",
            "dashboard",
            "site/data/treasury-data.js",
            "site/data/contribution-data.js",
        ],
        cwd=project_dir,
    )
    staged = normalized_git_paths(
        project_dir,
        git_output(project_dir, "diff", "--cached", "--name-only"),
    )
    unexpected = sorted(path for path in staged if not is_allowed_generated_path(path))
    if unexpected:
        raise AutomationError(
            "Staging included a file outside the generated-data allowlist: "
            + ", ".join(unexpected[:8])
        )
    ensure_privacy(project_dir, staged)
    run(["git", "diff", "--cached", "--check"], cwd=project_dir)

    message = (
        f"{ticket}: Refresh treasury and contribution data through "
        f"{display_date(through_date)}"
    )
    run(["git", "commit", "-m", message], cwd=project_dir)
    run(["git", "push", remote, branch], cwd=project_dir)
    commit = git_output(project_dir, "rev-parse", "--short", "HEAD")
    print(f"Published generated dashboard data in {commit} on {branch}.")
    return commit


def send_notification(title: str, message: str) -> None:
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return
    script = (
        f"display notification {json.dumps(message)} "
        f"with title {json.dumps(title)}"
    )
    subprocess.run(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise AutomationError(
                "Another scheduled refresh is already running; no second attempt was made."
            ) from error
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.expanduser().resolve()
    lock_path = project_dir / ".foe-dashboard-refresh.lock"
    try:
        with exclusive_lock(lock_path):
            if args.validate_only:
                run_offline_validation(project_dir)
                run(
                    [
                        sys.executable,
                        "-B",
                        "export_forge_hammer_treasury.py",
                        "--dry-run",
                    ],
                    cwd=project_dir,
                )
                print("Scheduled refresh validation passed; no game request was sent.")
                return 0

            ensure_clean_start(project_dir)
            ensure_remote_is_current(project_dir, args.remote, args.branch)
            run_offline_validation(project_dir)
            previous_treasury_dates = treasury_snapshot_dates(project_dir)
            # This is the only exporter invocation in an actual scheduled run.
            run(
                [sys.executable, "-B", "export_forge_hammer_treasury.py"],
                cwd=project_dir,
            )
            current_treasury_dates = treasury_snapshot_dates(project_dir)
            ensure_treasury_history_preserved(
                previous_treasury_dates,
                current_treasury_dates,
            )
            treasury_date, contribution_date = validate_generated_metadata(project_dir)
            run_offline_validation(project_dir)
            changes = ensure_only_generated_changes(project_dir)
            through_date = min(treasury_date, contribution_date)
            if args.publish:
                publish_generated_changes(
                    project_dir,
                    paths=changes,
                    ticket=args.ticket,
                    remote=args.remote,
                    branch=args.branch,
                    through_date=through_date,
                )
            elif changes:
                print("Dashboard refreshed locally; automatic publishing is disabled.")
            if args.notify:
                send_notification(
                    "Guild dashboard refresh complete",
                    f"Treasury and contributions are current through {through_date.isoformat()}.",
                )
            return 0
    except (AutomationError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"Scheduled refresh failed: {error}", file=sys.stderr)
        print("No automatic retry will be attempted.", file=sys.stderr)
        if args.notify:
            send_notification(
                "Guild dashboard refresh needs attention",
                "The one-shot refresh stopped safely. Review the local automation log.",
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
