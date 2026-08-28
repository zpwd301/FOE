from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from generate_contribution_dashboard import (
    REQUIRED_COLUMNS,
    TRANSACTION_ID_COLUMN,
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
    def row(*, name: str = "Clipper", amount: int = 5) -> list[str]:
        return [
            "853996216",
            name,
            "24 - Stellar Age Discovery",
            "Xenocrystals",
            str(amount),
            "Guild treasury donation",
            "8/26/2026 8:00:00 PM",
        ]

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
