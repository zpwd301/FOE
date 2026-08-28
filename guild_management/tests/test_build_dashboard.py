from __future__ import annotations

import unittest

from build_dashboard import build_contribution_summary_payload


class ContributionSummaryTests(unittest.TestCase):
    @staticmethod
    def record(
        timestamp: str,
        player_id: str,
        player_name: str,
        era: str,
        amount: int,
        good: str = "Good",
    ) -> list[object]:
        return [
            timestamp,
            player_id,
            player_name,
            era,
            good,
            amount,
            "Building production",
        ]

    def test_era_contributors_are_aggregated_ranked_limited_and_period_specific(self) -> None:
        future = "14 - Future Era"
        payload = {
            "meta": {"latestTimestamp": "2026-08-27T12:00:00"},
            "records": [
                self.record("2026-08-27T11:00:00", "1", "Zara", future, 40, "Algae"),
                self.record("2026-08-27T10:00:00", "1", "Zara", future, 60, "Robots"),
                self.record("2026-08-27T09:00:00", "2", "Amy", future, 80),
                self.record("2026-08-27T08:00:00", "3", "Ben", future, 80),
                self.record("2026-08-27T07:00:00", "4", "Cara", future, 50),
                self.record("2026-08-17T11:00:00", "4", "Cara", future, 100),
            ],
        }

        summary = build_contribution_summary_payload(payload)

        self.assertEqual(
            summary["periods"]["3"]["eraContributors"][future],
            [
                {"id": "1", "name": "Zara", "total": 100},
                {"id": "2", "name": "Amy", "total": 80},
                {"id": "3", "name": "Ben", "total": 80},
            ],
        )
        self.assertEqual(
            summary["periods"]["30"]["eraContributors"][future],
            [
                {"id": "4", "name": "Cara", "total": 150},
                {"id": "1", "name": "Zara", "total": 100},
                {"id": "2", "name": "Amy", "total": 80},
            ],
        )


if __name__ == "__main__":
    unittest.main()
