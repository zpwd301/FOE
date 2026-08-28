from __future__ import annotations

import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from generate_contribution_dashboard import (
    REQUIRED_COLUMNS,
    TRANSACTION_ID_COLUMN,
    append_audited_rows,
    audit_inventory_delta,
    build_payload,
    merge_exports,
)


class ContributionMergeTests(unittest.TestCase):
    def write_export(
        self,
        path: Path,
        rows: list[list[str]],
        *,
        include_transaction_id: bool = False,
    ) -> None:
        columns = list(REQUIRED_COLUMNS)
        if include_transaction_id:
            columns.append(TRANSACTION_ID_COLUMN)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";", lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(rows)

    @staticmethod
    def row(
        *,
        name: str = "Clipper",
        amount: int = 5,
        good: str = "Xenocrystals",
        timestamp: str = "8/26/2026 8:00:00 PM",
    ) -> list[str]:
        return [
            "853996216",
            name,
            "24 - Stellar Age Discovery",
            good,
            str(amount),
            "Guild treasury donation",
            timestamp,
        ]

    @staticmethod
    def write_treasury(path: Path, values: list[int]) -> None:
        goods = [
            "Xenocrystals",
            "Glyph Circuits",
            "Metamorphic Alloys",
            "Resonance Cores",
            "Psionic Conduits",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";", lineterminator="\n")
            writer.writerow(["DateTime", *goods])
            writer.writerow(["2026-08-26 00:00:00", *values])

    @staticmethod
    def production_batch(amounts: list[int]) -> list[list[str]]:
        goods = [
            "Glyph Circuits",
            "Metamorphic Alloys",
            "Psionic Conduits",
            "Resonance Cores",
            "Xenocrystals",
        ]
        return [
            [
                "19531771",
                "JOsborne32",
                "24 - Stellar Age Discovery",
                good,
                str(amount),
                "Building production",
                "8/26/2026 9:35:00 PM",
            ]
            for good, amount in zip(goods, amounts, strict=True)
        ]

    def test_preserves_repeated_identical_rows_within_one_legacy_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-26.csv"
            self.write_export(path, [self.row() for _ in range(9)])

            rows, overlap_count = merge_exports([path])

        self.assertEqual(len(rows), 9)
        self.assertEqual(sum(int(row["amount"]) for row in rows), 45)
        self.assertEqual(overlap_count, 0)

    def test_uses_maximum_occurrence_count_across_legacy_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "GuildTreasury-2026-08-26.csv"
            second = Path(directory) / "GuildTreasury-2026-08-27.csv"
            self.write_export(first, [self.row(name="Old name") for _ in range(9)])
            self.write_export(second, [self.row(name="Current name") for _ in range(10)])

            rows, overlap_count = merge_exports([first, second])

        self.assertEqual(len(rows), 10)
        self.assertEqual(overlap_count, 9)
        self.assertEqual({str(row["playerName"]) for row in rows}, {"Current name"})

    def test_exact_transaction_ids_deduplicate_within_and_across_exports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "GuildTreasury-2026-08-26.csv"
            second = Path(directory) / "GuildTreasury-2026-08-27.csv"
            repeated = [*self.row(), "log-1"]
            distinct = [*self.row(), "log-2"]
            self.write_export(
                first,
                [repeated, repeated],
                include_transaction_id=True,
            )
            self.write_export(
                second,
                [repeated, distinct],
                include_transaction_id=True,
            )

            rows, overlap_count = merge_exports([first, second])

        self.assertEqual(len(rows), 2)
        self.assertEqual(overlap_count, 2)
        self.assertEqual(
            {str(row["transactionId"]) for row in rows},
            {"log-1", "log-2"},
        )

    def test_closed_history_baseline_replaces_unstable_legacy_multiplicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.csv"
            current = Path(directory) / "current.csv"
            self.write_export(baseline, [self.row() for _ in range(5)])
            self.write_export(
                current,
                [
                    *[self.row() for _ in range(7)],
                    self.row(timestamp="8/26/2026 9:00:00 PM"),
                ],
            )

            rows, overlap_count = merge_exports(
                [current],
                closed_history_baseline=baseline,
            )

        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(int(row["amount"]) for row in rows), 30)
        self.assertEqual(overlap_count, 2)

    def test_audits_inventory_delta_for_every_good(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_contribution = root / "baseline-contribution.csv"
            current_contribution = root / "current-contribution.csv"
            baseline_treasury = root / "baseline-treasury.csv"
            current_treasury = root / "current-treasury.csv"
            self.write_export(baseline_contribution, [self.row()])
            self.write_export(
                current_contribution,
                [
                    self.row(),
                    self.row(timestamp="8/26/2026 9:00:00 PM"),
                ],
            )
            self.write_treasury(baseline_treasury, [100, 100, 100, 100, 100])
            self.write_treasury(current_treasury, [105, 100, 100, 100, 100])

            audit = audit_inventory_delta(
                baseline_contribution,
                current_contribution,
                baseline_treasury,
                current_treasury,
            )

        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["goodsChecked"], 5)
        self.assertEqual(audit["agesChecked"], 1)

    def test_rejects_any_per_good_inventory_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_contribution = root / "baseline-contribution.csv"
            current_contribution = root / "current-contribution.csv"
            baseline_treasury = root / "baseline-treasury.csv"
            current_treasury = root / "current-treasury.csv"
            self.write_export(baseline_contribution, [self.row()])
            self.write_export(
                current_contribution,
                [
                    self.row(),
                    self.row(timestamp="8/26/2026 9:00:00 PM"),
                ],
            )
            self.write_treasury(baseline_treasury, [100, 100, 100, 100, 100])
            self.write_treasury(current_treasury, [106, 100, 100, 100, 100])

            with self.assertRaisesRegex(
                ValueError,
                r"failed for 1 of 5 goods.*Xenocrystals \(\+1\)",
            ):
                audit_inventory_delta(
                    baseline_contribution,
                    current_contribution,
                    baseline_treasury,
                    current_treasury,
                )

    def test_extends_canonical_history_without_reopening_old_multiplicity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current.csv"
            self.write_export(
                current,
                [
                    *[self.row() for _ in range(7)],
                    self.row(timestamp="8/26/2026 9:00:00 PM"),
                ],
            )
            baseline_rows = [
                {
                    "timestamp": dt.datetime(2026, 8, 26, 20, 0),
                    "playerId": "853996216",
                    "playerName": "Clipper",
                    "era": "24 - Stellar Age Discovery",
                    "good": "Xenocrystals",
                    "amount": 5,
                    "message": "Guild treasury donation",
                    "transactionId": "",
                }
                for _ in range(5)
            ]
            payload = build_payload(baseline_rows, "GoE")

            rows = append_audited_rows(
                payload,
                current,
                dt.datetime(2026, 8, 26, 20, 0),
            )

        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(int(row["amount"]) for row in rows), 30)

    def test_keeps_positive_and_negative_rows_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-26.csv"
            self.write_export(path, [self.row(amount=5), self.row(amount=-5)])

            rows, overlap_count = merge_exports([path])

        self.assertEqual({int(row["amount"]) for row in rows}, {-5, 5})
        self.assertEqual(overlap_count, 0)

    def test_removes_only_malformed_mixed_amount_production_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "GuildTreasury-2026-08-27.csv"
            source_rows = [
                *self.production_batch([66, 66, 66, 66, 66]),
                *self.production_batch([66, 60, 60, 60, 60]),
                *self.production_batch([60, 60, 60, 60, 60]),
            ]
            self.write_export(path, source_rows)

            rows, overlap_count = merge_exports([path])

        self.assertEqual(len(rows), 10)
        self.assertEqual(overlap_count, 5)
        self.assertEqual(sum(int(row["amount"]) for row in rows), 630)


if __name__ == "__main__":
    unittest.main()
