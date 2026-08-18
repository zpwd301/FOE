#!/usr/bin/env python3
"""Install or remove the local once-daily guild dashboard LaunchAgent."""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LABEL = "uk.z301.foe-guild-dashboard-refresh"


class InstallError(RuntimeError):
    """A safe LaunchAgent installation failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install a once-daily macOS LaunchAgent for the fail-closed guild "
            "dashboard refresh. Installation never starts the job immediately."
        )
    )
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--hour", type=int, default=2)
    parser.add_argument("--minute", type=int, default=15)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser.parse_args()


def validate_schedule(hour: int, minute: int) -> None:
    if not 0 <= hour <= 23:
        raise InstallError("Hour must be between 0 and 23.")
    if not 0 <= minute <= 59:
        raise InstallError("Minute must be between 0 and 59.")


def launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def build_plist(
    *,
    project_dir: Path,
    python: Path,
    label: str,
    hour: int,
    minute: int,
    publish: bool,
) -> dict[str, object]:
    runner = project_dir / "automation/run_daily_refresh.py"
    arguments = [
        str(python),
        "-B",
        str(runner),
        "--project-dir",
        str(project_dir),
        "--branch",
        "main",
        "--notify",
    ]
    if publish:
        arguments.append("--publish")
    environment: dict[str, str] = {}
    if path_value := os.environ.get("PATH"):
        environment["PATH"] = path_value

    payload: dict[str, object] = {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(project_dir),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(project_dir / ".foe-launchd.out.log"),
        "StandardErrorPath": str(project_dir / ".foe-launchd.err.log"),
    }
    if environment:
        payload["EnvironmentVariables"] = environment
    return payload


def launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("launchctl")
    if not executable:
        raise InstallError("launchctl is unavailable; this installer requires macOS.")
    return subprocess.run(
        [executable, *arguments],
        check=check,
        text=True,
        capture_output=True,
    )


def unload(domain: str, plist_path: Path) -> None:
    result = launchctl("bootout", domain, str(plist_path), check=False)
    if result.returncode not in {0, 3, 5, 113}:
        detail = result.stderr.strip() or result.stdout.strip()
        raise InstallError(f"Could not unload the existing LaunchAgent: {detail}")


def write_plist(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    args = parse_args()
    try:
        validate_schedule(args.hour, args.minute)
        if sys.platform != "darwin":
            raise InstallError("The daily LaunchAgent installer supports macOS only.")
        if not args.label or any(character.isspace() for character in args.label):
            raise InstallError("LaunchAgent label must be non-empty and contain no spaces.")

        project_dir = args.project_dir.expanduser().resolve()
        python = args.python.expanduser().resolve()
        runner = project_dir / "automation/run_daily_refresh.py"
        if not runner.is_file():
            raise InstallError(f"Daily refresh runner is missing: {runner}")
        if not python.is_file() or not os.access(python, os.X_OK):
            raise InstallError(f"Python executable is unavailable: {python}")

        plist_path = launch_agent_path(args.label)
        domain = f"gui/{os.getuid()}"
        if args.uninstall:
            if args.dry_run:
                print(f"Would unload and remove LaunchAgent {args.label}.")
                return 0
            unload(domain, plist_path)
            plist_path.unlink(missing_ok=True)
            print(f"Removed LaunchAgent {args.label}.")
            return 0

        payload = build_plist(
            project_dir=project_dir,
            python=python,
            label=args.label,
            hour=args.hour,
            minute=args.minute,
            publish=not args.no_publish,
        )
        if args.dry_run:
            print(
                f"LaunchAgent {args.label} would run daily at "
                f"{args.hour:02d}:{args.minute:02d}."
            )
            print("RunAtLoad is disabled and no KeepAlive policy is configured.")
            return 0

        unload(domain, plist_path)
        write_plist(plist_path, payload)
        launchctl("bootstrap", domain, str(plist_path))
        launchctl("enable", f"{domain}/{args.label}")
        print(
            f"Installed LaunchAgent {args.label}; next scheduled time is "
            f"{args.hour:02d}:{args.minute:02d} local time."
        )
        print("The job was not started during installation.")
        return 0
    except (InstallError, OSError, subprocess.CalledProcessError) as error:
        print(f"LaunchAgent installation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
