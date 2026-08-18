from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation.install_launch_agent import (
    InstallError,
    build_plist,
    validate_schedule,
)
from automation.run_daily_refresh import (
    AutomationError,
    ensure_only_generated_changes,
    ensure_privacy,
    ensure_treasury_history_preserved,
    exclusive_lock,
    is_allowed_generated_path,
    normalized_git_paths,
    project_changes,
    publish_generated_changes,
    treasury_snapshot_dates,
    validate_generated_metadata,
)


class GeneratedPathTests(unittest.TestCase):
    def test_allows_only_dashboard_outputs_and_two_source_payloads(self) -> None:
        self.assertTrue(is_allowed_generated_path("dashboard/index.html"))
        self.assertTrue(
            is_allowed_generated_path("site/data/treasury-data.js")
        )
        self.assertTrue(
            is_allowed_generated_path("site/data/contribution-data.js")
        )
        self.assertFalse(is_allowed_generated_path("README.md"))
        self.assertFalse(is_allowed_generated_path("site/assets/app.js"))

    def test_rejects_an_export_that_changes_source_code(self) -> None:
        with mock.patch(
            "automation.run_daily_refresh.project_changes",
            return_value={"dashboard/index.html", "export_forge_hammer_treasury.py"},
        ):
            with self.assertRaisesRegex(AutomationError, "outside the generated"):
                ensure_only_generated_changes(Path("."))

    def test_normalizes_paths_reported_from_the_repository_root(self) -> None:
        with mock.patch(
            "automation.run_daily_refresh.git_output",
            return_value="guild_management/",
        ):
            self.assertEqual(
                normalized_git_paths(
                    Path("."),
                    "guild_management/dashboard/index.html\nREADME.md\n",
                ),
                {"dashboard/index.html", "README.md"},
            )


class MetadataTests(unittest.TestCase):
    def test_requires_every_contribution_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            data_dir = project / "site/data"
            input_dir = project / "input/guild-goods-contribution"
            data_dir.mkdir(parents=True)
            input_dir.mkdir(parents=True)
            sources = [
                "GuildTreasury-2026-08-17.csv",
                "GuildTreasury-2026-08-18.csv",
            ]
            for name in sources:
                (input_dir / name).write_text("placeholder\n", encoding="utf-8")
            treasury = {
                "meta": {
                    "firstDate": "2026-08-18",
                    "latestDate": "2026-08-18",
                    "availableDays": 1,
                },
                "dates": ["2026-08-18"],
                "goods": [],
            }
            contribution = {
                "meta": {
                    "latestTimestamp": "2026-08-18T03:00:00",
                    "sourceFileCount": 2,
                    "sourceFiles": sources,
                    "duplicateRecordCount": 10,
                },
                "records": [],
            }
            (data_dir / "treasury-data.js").write_text(
                "window.TREASURY_DATA = " + json.dumps(treasury) + ";\n",
                encoding="utf-8",
            )
            (data_dir / "contribution-data.js").write_text(
                "window.CONTRIBUTION_DATA = " + json.dumps(contribution) + ";\n",
                encoding="utf-8",
            )

            treasury_date, contribution_date = validate_generated_metadata(project)
            self.assertEqual(treasury_date.isoformat(), "2026-08-18")
            self.assertEqual(contribution_date.isoformat(), "2026-08-18")

            (input_dir / "GuildTreasury-2026-08-16.csv").write_text(
                "placeholder\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AutomationError, "every available"):
                validate_generated_metadata(project)

    def test_rejects_a_treasury_history_regression(self) -> None:
        previous = tuple(
            dt.date(2026, 8, day)
            for day in (15, 16, 17)
        )
        current = tuple(
            dt.date(2026, 8, day)
            for day in (17, 18)
        )
        with self.assertRaisesRegex(AutomationError, "history regressed"):
            ensure_treasury_history_preserved(previous, current)

    def test_accepts_an_appended_treasury_snapshot(self) -> None:
        previous = tuple(dt.date(2026, 8, day) for day in (15, 16, 17))
        current = (*previous, dt.date(2026, 8, 18))
        ensure_treasury_history_preserved(previous, current)

    def test_rejects_inconsistent_treasury_snapshot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            data_dir = project / "site/data"
            data_dir.mkdir(parents=True)
            treasury = {
                "meta": {
                    "firstDate": "2026-08-17",
                    "latestDate": "2026-08-18",
                    "availableDays": 1,
                },
                "dates": ["2026-08-17", "2026-08-18"],
                "goods": [],
            }
            (data_dir / "treasury-data.js").write_text(
                "window.TREASURY_DATA = " + json.dumps(treasury) + ";\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AutomationError, "metadata is inconsistent"):
                treasury_snapshot_dates(project)


class PrivacyTests(unittest.TestCase):
    def test_rejects_the_current_home_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            output = project / "dashboard/index.html"
            output.parent.mkdir()
            output.write_text(f"source={Path.home()}\n", encoding="utf-8")
            with self.assertRaisesRegex(AutomationError, "personal absolute path"):
                ensure_privacy(project, {"dashboard/index.html"})


class PublishingTests(unittest.TestCase):
    def test_commits_and_pushes_only_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            project = root / "guild_management"
            dashboard = project / "dashboard"
            data_dir = project / "site/data"
            dashboard.mkdir(parents=True)
            data_dir.mkdir(parents=True)
            (project / "README.md").write_text("source documentation\n", encoding="utf-8")
            (dashboard / "index.html").write_text("old dashboard\n", encoding="utf-8")
            (data_dir / "treasury-data.js").write_text("old treasury\n", encoding="utf-8")
            (data_dir / "contribution-data.js").write_text(
                "old contributions\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "init", "-b", "main", str(root)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Automation Test"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "automation@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=root,
                check=True,
                capture_output=True,
            )

            remote = Path(directory) / "remote.git"
            subprocess.run(
                ["git", "init", "--bare", str(remote)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", str(remote)],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "main"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            hook = root / ".git/hooks/pre-push"
            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(hook, 0o700)

            (dashboard / "index.html").write_text("new dashboard\n", encoding="utf-8")
            (dashboard / "data.new.js").write_text("new asset\n", encoding="utf-8")
            (data_dir / "treasury-data.js").write_text("new treasury\n", encoding="utf-8")
            (data_dir / "contribution-data.js").write_text(
                "new contributions\n",
                encoding="utf-8",
            )
            changes = project_changes(project)
            commit = publish_generated_changes(
                project,
                paths=changes,
                ticket="FOE-30",
                remote="origin",
                branch="main",
                through_date=dt.date(2026, 8, 18),
            )

            self.assertIsNotNone(commit)
            message = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(
                message,
                "FOE-30: Refresh treasury and contribution data through August 18",
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                subprocess.run(
                    ["git", "rev-parse", "origin/main"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
            )
            self.assertEqual(project_changes(project), set())


class LockTests(unittest.TestCase):
    def test_refuses_a_second_concurrent_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "refresh.lock"
            with exclusive_lock(lock):
                with self.assertRaisesRegex(AutomationError, "already running"):
                    with exclusive_lock(lock):
                        self.fail("A second lock should not be acquired")


class LaunchAgentTests(unittest.TestCase):
    def test_installs_one_daily_non_retrying_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            payload = build_plist(
                project_dir=project,
                python=Path("python3"),
                label="example.refresh",
                hour=2,
                minute=15,
                publish=True,
            )
            self.assertEqual(
                payload["StartCalendarInterval"],
                {"Hour": 2, "Minute": 15},
            )
            self.assertFalse(payload["RunAtLoad"])
            self.assertNotIn("KeepAlive", payload)
            self.assertIn("--publish", payload["ProgramArguments"])

    def test_rejects_invalid_schedule_values(self) -> None:
        with self.assertRaises(InstallError):
            validate_schedule(24, 0)
        with self.assertRaises(InstallError):
            validate_schedule(3, 60)


if __name__ == "__main__":
    unittest.main()
