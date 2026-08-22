from __future__ import annotations

import csv
import datetime as dt
import json
import os
import signal
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from export_forge_hammer_treasury import (
    BrowserConfig,
    BrowserExportError,
    DEFAULT_CHROME_USER_DATA_DIR,
    close_running_chrome_profile,
    chrome_is_running,
    ensure_attempt_allowed,
    find_contribution_cutoff,
    find_reference_header,
    launch_chrome,
    main,
    merge_treasury_csv_history,
    parse_args,
    validate_contribution_csv,
    validate_treasury_csv,
)
from generate_contribution_dashboard import REQUIRED_COLUMNS


def write_export(
    path: Path,
    *,
    last_date: dt.date,
    goods: int = 110,
    snapshots: int = 2,
    value_offset: int = 0,
) -> list[str]:
    header = ["DateTime", *[f"Good {index}" for index in range(goods)]]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(header)
        for index in range(snapshots):
            date = last_date - dt.timedelta(days=snapshots - index - 1)
            writer.writerow(
                [
                    f"{date.isoformat()} 00:00:00",
                    *range(value_offset + index, value_offset + index + goods),
                ]
            )
    return header


def write_contribution_export(
    path: Path,
    *,
    newest: dt.datetime,
    records: int,
    minute_step: int = 5,
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\r\n")
        writer.writerow(REQUIRED_COLUMNS)
        for index in range(records):
            timestamp = newest - dt.timedelta(minutes=index * minute_step)
            writer.writerow(
                [
                    "855340115",
                    "zpwd",
                    "18 - Space Age Mars",
                    "Fusion Reactors",
                    str(100 + index),
                    "Guild treasury donation",
                    timestamp.strftime("%-m/%-d/%Y %-I:%M:%S %p"),
                ]
            )


class CsvValidationTests(unittest.TestCase):
    def test_validates_a_forge_hammer_daily_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats-2026-08-17.csv"
            header = write_export(path, last_date=dt.date(2026, 8, 17))
            summary = validate_treasury_csv(
                path,
                expected_date=dt.date(2026, 8, 17),
                expected_header=header,
            )
            self.assertEqual(summary.goods, 110)
            self.assertEqual(summary.snapshots, 2)
            self.assertEqual(len(summary.sha256), 64)

    def test_rejects_a_stale_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats-2026-08-16.csv"
            write_export(path, last_date=dt.date(2026, 8, 16))
            with self.assertRaisesRegex(BrowserExportError, "not 2026-08-17"):
                validate_treasury_csv(path, expected_date=dt.date(2026, 8, 17))

    def test_rejects_changed_goods_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats-2026-08-17.csv"
            write_export(path, last_date=dt.date(2026, 8, 17), goods=105)
            with self.assertRaisesRegex(BrowserExportError, "105 goods; expected 110"):
                validate_treasury_csv(path, expected_date=dt.date(2026, 8, 17))

    def test_selects_latest_reference_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "stats-2026-08-15.csv"
            new = root / "stats-2026-08-16.csv"
            write_export(old, last_date=dt.date(2026, 8, 15))
            expected = write_export(new, last_date=dt.date(2026, 8, 16))
            os.utime(old, (1, 1))
            os.utime(new, (2, 2))
            self.assertEqual(find_reference_header(root), expected)

    def test_merges_a_single_profile_snapshot_into_the_longest_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "stats-2026-08-17.csv"
            short_history = root / "stats-2026-08-16.csv"
            downloaded = root / "download.csv"
            destination = root / "stats-2026-08-18.csv"
            header = write_export(
                history,
                last_date=dt.date(2026, 8, 17),
                snapshots=4,
            )
            write_export(
                short_history,
                last_date=dt.date(2026, 8, 16),
                snapshots=1,
            )
            write_export(
                downloaded,
                last_date=dt.date(2026, 8, 18),
                snapshots=1,
                value_offset=500,
            )

            merged, fresh, reference = merge_treasury_csv_history(
                downloaded,
                destination,
                input_dir=root,
                expected_date=dt.date(2026, 8, 18),
                expected_header=header,
            )

            self.assertEqual(fresh.snapshots, 1)
            self.assertEqual(merged.snapshots, 5)
            self.assertEqual(reference[0], history)
            with destination.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            self.assertEqual(rows[-1][0], "2026-08-18 00:00:00")
            self.assertEqual(rows[-1][1], "500")


class ContributionCsvValidationTests(unittest.TestCase):
    def test_finds_latest_export_and_subtracts_one_hour(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_contribution_export(
                root / "GuildTreasury-2026-08-14.csv",
                newest=dt.datetime(2026, 8, 14, 22, 0),
                records=10,
            )
            latest = root / "GuildTreasury-2026-08-16.csv"
            write_contribution_export(
                latest,
                newest=dt.datetime(2026, 8, 16, 10, 9),
                records=10,
            )
            reference, newest, cutoff = find_contribution_cutoff(root)
            self.assertEqual(reference, latest)
            self.assertEqual(newest, dt.datetime(2026, 8, 16, 10, 9))
            self.assertEqual(cutoff, dt.datetime(2026, 8, 16, 9, 9))

    def test_validates_when_final_page_first_row_crosses_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-17.csv"
            newest = dt.datetime(2026, 8, 17, 10, 0)
            write_contribution_export(path, newest=newest, records=20)
            summary = validate_contribution_csv(
                path,
                cutoff=dt.datetime(2026, 8, 17, 9, 15),
            )
            self.assertEqual(summary.records, 20)
            self.assertEqual(
                summary.final_page_first_timestamp,
                dt.datetime(2026, 8, 17, 9, 10),
            )

    def test_allows_full_last_page_when_server_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-17.csv"
            write_contribution_export(
                path,
                newest=dt.datetime(2026, 8, 17, 10, 0),
                records=20,
            )
            summary = validate_contribution_csv(
                path,
                cutoff=dt.datetime(2026, 8, 17, 9, 0),
            )
            self.assertEqual(summary.records, 20)

    def test_allows_partial_last_page_when_server_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-17.csv"
            write_contribution_export(
                path,
                newest=dt.datetime(2026, 8, 17, 10, 0),
                records=13,
            )
            summary = validate_contribution_csv(
                path,
                cutoff=dt.datetime(2026, 8, 17, 8, 0),
            )
            self.assertEqual(summary.records, 13)

    def test_allows_forge_hammer_timestamp_ties_and_minor_inversions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-17.csv"
            write_contribution_export(
                path,
                newest=dt.datetime(2026, 8, 17, 10, 0),
                records=20,
            )
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle, delimiter=";"))
            rows[11], rows[12] = rows[12], rows[11]
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                csv.writer(handle, delimiter=";", lineterminator="\r\n").writerows(rows)
            summary = validate_contribution_csv(
                path,
                cutoff=dt.datetime(2026, 8, 17, 9, 0),
            )
            self.assertEqual(summary.newest_timestamp, dt.datetime(2026, 8, 17, 10, 0))
            self.assertEqual(summary.oldest_timestamp, dt.datetime(2026, 8, 17, 8, 25))


class AttemptGuardTests(unittest.TestCase):
    def test_refuses_same_day_retry_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                '{"date":"2026-08-17","status":"failed"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(BrowserExportError, "Refusing an automatic retry"):
                ensure_attempt_allowed(state, dt.date(2026, 8, 17))

    def test_allows_a_new_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                '{"date":"2026-08-16","status":"failed"}\n',
                encoding="utf-8",
            )
            ensure_attempt_allowed(state, dt.date(2026, 8, 17))

    def test_allows_an_explicitly_authorized_same_day_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                '{"date":"2026-08-17","status":"failed"}\n',
                encoding="utf-8",
            )
            ensure_attempt_allowed(
                state,
                dt.date(2026, 8, 17),
                allow_same_day_retry=True,
            )

    def test_refuses_same_day_retry_after_success_when_output_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                '{"date":"2026-08-17","status":"success"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(BrowserExportError, "Refusing an automatic retry"):
                ensure_attempt_allowed(state, dt.date(2026, 8, 17))


class CommandLineTests(unittest.TestCase):
    def test_refreshes_dashboards_by_default(self) -> None:
        with mock.patch("sys.argv", ["export_forge_hammer_treasury.py"]):
            self.assertTrue(parse_args().refresh)

    def test_can_explicitly_stop_after_saving_csvs(self) -> None:
        with mock.patch(
            "sys.argv",
            ["export_forge_hammer_treasury.py", "--no-refresh"],
        ):
            self.assertFalse(parse_args().refresh)

    def test_rebuild_is_a_refresh_compatibility_alias(self) -> None:
        with mock.patch(
            "sys.argv",
            ["export_forge_hammer_treasury.py", "--rebuild"],
        ):
            self.assertTrue(parse_args().refresh)

    def test_can_close_the_configured_running_profile(self) -> None:
        with mock.patch(
            "sys.argv",
            ["export_forge_hammer_treasury.py", "--close-running-profile"],
        ):
            self.assertTrue(parse_args().close_running_profile)


class ExistingExportWorkflowTests(unittest.TestCase):
    def test_refreshes_both_dashboards_without_opening_chrome(self) -> None:
        today = dt.datetime.now().astimezone().date()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            contribution_dir = input_dir / "guild-goods-contribution"
            contribution_dir.mkdir(parents=True)

            write_export(
                input_dir / f"stats-{today - dt.timedelta(days=1)}.csv",
                last_date=today - dt.timedelta(days=1),
            )
            treasury = input_dir / f"stats-{today}.csv"
            write_export(treasury, last_date=today)

            write_contribution_export(
                contribution_dir
                / f"GuildTreasury-{today - dt.timedelta(days=1)}.csv",
                newest=dt.datetime.combine(
                    today - dt.timedelta(days=1),
                    dt.time(10, 0),
                ),
                records=20,
            )
            contribution = contribution_dir / f"GuildTreasury-{today}.csv"
            write_contribution_export(
                contribution,
                newest=dt.datetime.combine(today, dt.time(10, 0)),
                records=20,
            )

            config = BrowserConfig(
                world="us24",
                chrome_binary=root / "chrome",
                user_data_dir=root / "chrome-data",
                profile_directory="Profile 3",
                download_dir=root / "downloads",
                input_dir=input_dir,
                contribution_input_dir=contribution_dir,
                state_file=root / "state.json",
                timeout_seconds=600,
            )
            args = mock.Mock(dry_run=False, refresh=True)
            with (
                mock.patch(
                    "export_forge_hammer_treasury.parse_args",
                    return_value=args,
                ),
                mock.patch(
                    "export_forge_hammer_treasury.load_browser_config",
                    return_value=config,
                ),
                mock.patch(
                    "export_forge_hammer_treasury.rebuild_treasury_dashboard"
                ) as refresh_treasury,
                mock.patch(
                    "export_forge_hammer_treasury.rebuild_contribution_dashboard"
                ) as refresh_contributions,
                mock.patch("export_forge_hammer_treasury.launch_chrome") as launch_chrome,
            ):
                self.assertEqual(main(), 0)

            refresh_treasury.assert_called_once_with(treasury)
            refresh_contributions.assert_called_once_with(contribution_dir)
            launch_chrome.assert_not_called()


class ChromeProfileSafetyTests(unittest.TestCase):
    @staticmethod
    def config(root: Path, *, user_data_dir: Path | None = None) -> BrowserConfig:
        return BrowserConfig(
            world="us24",
            chrome_binary=Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ),
            user_data_dir=user_data_dir or root / "chrome-data",
            profile_directory="Profile 8",
            download_dir=root / "downloads",
            input_dir=root / "input",
            contribution_input_dir=root / "contributions",
            state_file=root / "state.json",
            timeout_seconds=600,
            world_name="Yorkton",
        )

    def test_launcher_passes_the_world_display_name_to_the_companion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = BrowserConfig(
                world="us24",
                chrome_binary=root / "chrome",
                user_data_dir=root / "chrome-data",
                profile_directory="Profile 8",
                download_dir=root / "downloads",
                input_dir=root / "input",
                contribution_input_dir=root / "contributions",
                state_file=root / "state.json",
                timeout_seconds=600,
                world_name="Yorkton",
            )
            with mock.patch("export_forge_hammer_treasury.subprocess.Popen") as popen:
                launch_chrome(
                    config,
                    "nonce",
                    export_treasury=True,
                    export_contributions=True,
                    contribution_cutoff=dt.datetime(2026, 8, 17, 21, 55),
                    live_debug=True,
                )
            command = popen.call_args.args[0]
            self.assertIn("world_name=Yorkton", command[-1])
            self.assertIn("live_debug=1", command[-1])

    def test_default_data_directory_treats_any_chrome_as_a_conflict(self) -> None:
        result = mock.Mock(returncode=0, stdout="123 Google Chrome\n")
        with (
            mock.patch("export_forge_hammer_treasury.sys.platform", "darwin"),
            mock.patch(
                "export_forge_hammer_treasury.subprocess.run",
                return_value=result,
            ),
        ):
            self.assertTrue(
                chrome_is_running(Path("chrome"), DEFAULT_CHROME_USER_DATA_DIR)
            )

    def test_dedicated_data_directory_ignores_regular_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = mock.Mock(returncode=0, stdout="123 Google Chrome\n")
            with (
                mock.patch("export_forge_hammer_treasury.sys.platform", "darwin"),
                mock.patch(
                    "export_forge_hammer_treasury.subprocess.run",
                    return_value=result,
                ),
            ):
                self.assertFalse(chrome_is_running(Path("chrome"), Path(directory)))

    def test_dedicated_data_directory_detects_its_own_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory).resolve()
            result = mock.Mock(
                returncode=0,
                stdout=f"123 Google Chrome --user-data-dir={data_dir}\n",
            )
            with (
                mock.patch("export_forge_hammer_treasury.sys.platform", "darwin"),
                mock.patch(
                    "export_forge_hammer_treasury.subprocess.run",
                    return_value=result,
                ),
            ):
                self.assertTrue(chrome_is_running(Path("chrome"), data_dir))

    def test_closes_only_the_exact_automation_profile_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.config(root)
            data_dir = config.user_data_dir.resolve()
            command = (
                f"{config.chrome_binary} --user-data-dir={data_dir} "
                f"--profile-directory={config.profile_directory} --new-window"
            )
            running = mock.Mock(returncode=0, stdout=f"123 {command}\n")
            stopped = mock.Mock(returncode=1, stdout="")
            with (
                mock.patch("export_forge_hammer_treasury.sys.platform", "darwin"),
                mock.patch(
                    "export_forge_hammer_treasury.subprocess.run",
                    side_effect=[running, stopped, stopped],
                ),
                mock.patch("export_forge_hammer_treasury.os.kill") as kill,
            ):
                self.assertTrue(close_running_chrome_profile(config))
            kill.assert_called_once_with(123, signal.SIGTERM)

    def test_refuses_to_close_unrelated_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(
                Path(directory),
                user_data_dir=DEFAULT_CHROME_USER_DATA_DIR,
            )
            unrelated = mock.Mock(
                returncode=0,
                stdout=f"123 {config.chrome_binary}\n",
            )
            with (
                mock.patch("export_forge_hammer_treasury.sys.platform", "darwin"),
                mock.patch(
                    "export_forge_hammer_treasury.subprocess.run",
                    return_value=unrelated,
                ),
                mock.patch("export_forge_hammer_treasury.os.kill") as kill,
            ):
                with self.assertRaisesRegex(BrowserExportError, "does not match"):
                    close_running_chrome_profile(config)
            kill.assert_not_called()


class CompanionExtensionSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extension_dir = Path(__file__).parents[1] / "chrome/forge-hammer-treasury-exporter"
        cls.source = (cls.extension_dir / "export-treasury.js").read_text(encoding="utf-8")
        cls.manifest = json.loads(
            (cls.extension_dir / "manifest.json").read_text(encoding="utf-8")
        )

    def test_hook_runs_before_the_game_client(self) -> None:
        content_script = self.manifest["content_scripts"][0]
        self.assertEqual(content_script["run_at"], "document_start")
        self.assertEqual(content_script["world"], "MAIN")
        self.assertEqual(content_script["matches"], ["https://*.forgeofempires.com/*"])

    def test_uses_the_game_treasury_event_and_forge_hammer_correlation(self) -> None:
        self.assertIn("WindowEvent/CLOSE_ALL_WINDOW", self.source)
        self.assertIn("new WindowEvent(closeAllWindowsEventType)", self.source)
        self.assertIn("ShowClanWindowCommand_Event", self.source)
        self.assertIn("new ShowClanWindowEvent(null, 'treasury')", self.source)
        self.assertLess(
            self.source.index("closeAllGameWindowsOnce(windowDispatcher)"),
            self.source.index("triggerGameTreasuryRefreshOnce(dispatcher)"),
        )
        self.assertIn("addRequestHandler('ClanService', 'getTreasuryBag'", self.source)
        self.assertIn("data?.requestId !== outgoingRequest.requestId", self.source)

    def test_uses_official_contribution_pagination_and_forge_hammer_export(self) -> None:
        self.assertIn("openfl.events.EventDispatcher", self.source)
        self.assertIn("gameHooks.dispatchers.add(this)", self.source)
        self.assertIn("ConversationWindowEvent/REQUEST_MESSAGE_CENTER", self.source)
        self.assertIn("ConversationWindowEvent/OPEN_GUILD_CONTRIBUTION", self.source)
        self.assertIn("addRequestHandler('ClanService', 'getTreasuryLogs'", self.source)
        self.assertIn("observer.expectOffset(page * contributionPageSize)", self.source)
        self.assertIn("await sleep(contributionPageDelayMs)", self.source)
        self.assertIn("model.set_currentPage(page)", self.source)
        self.assertIn("Treasury.Export()", self.source)

    def test_companion_does_not_construct_a_network_request(self) -> None:
        self.assertNotIn("new XMLHttpRequest", self.source)
        self.assertNotIn("fetch(", self.source)
        self.assertNotIn("setInterval(", self.source)

    def test_manual_capture_is_passive_and_records_the_official_flow(self) -> None:
        self.assertIn("manual_capture", self.source)
        self.assertIn("[GoE manual capture]", self.source)
        self.assertIn("event-dispatched", self.source)
        self.assertIn("treasury-log-request", self.source)
        self.assertIn("treasury-log-response", self.source)
        self.assertIn("manualCapture ? startManualCapture() : run()", self.source)

    def test_companion_has_an_explicit_one_shot_guard(self) -> None:
        self.assertIn("triggerGameTreasuryRefreshOnce", self.source)
        self.assertIn("gameHooks.treasuryTriggerStarted = true", self.source)
        self.assertIn("gameHooks.contributionTriggerStarted = true", self.source)
        self.assertIn("no retry was made", self.source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the landing smoke test")
    def test_landing_flow_clicks_play_and_yorkton_once(self) -> None:
        result = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("forge_hammer_landing_companion_smoke.js")),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the companion smoke test")
    def test_companion_offline_flow_triggers_exactly_once(self) -> None:
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("forge_hammer_companion_smoke.js"))],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the companion smoke test")
    def test_contribution_pages_advance_once_until_cutoff(self) -> None:
        result = subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("forge_hammer_contribution_companion_smoke.js")),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
