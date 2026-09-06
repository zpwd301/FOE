#!/usr/bin/env python3
"""Derive level 202-301 contributor rewards from the sourced level 1-201 data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_dataset import MAX_LEVEL, expand_contributor_rewards


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/contributor-rewards-source.json"),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/gb-analysis.json"),
    )
    return parser.parse_args()


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    fp_source = {
        int(era_id): values[: source.get("exactThroughTargetLevel", 201)]
        for era_id, values in dataset["rewardP1ByEra"].items()
    }
    expanded = expand_contributor_rewards(source, fp_source, MAX_LEVEL)

    dataset["rewardP1ByEra"] = expanded["fpP1ByEra"]
    dataset["medalP1ByEra"] = expanded["medalP1ByEra"]
    dataset["blueprintsByLevel"] = expanded["blueprintsByLevel"]
    dataset["sources"]["contributorRewards"].update(
        {
            "throughTargetLevel": MAX_LEVEL,
            "exactThroughTargetLevel": expanded["exactThroughTargetLevel"],
            "estimatedFromTargetLevel": expanded["estimatedFromTargetLevel"],
            "estimation": expanded["estimation"],
            "fpObservations": expanded.get("fpObservations", {}),
            "medalObservations": expanded.get("medalObservations", {}),
            "directCapturedRewards": expanded["directCapturedRewards"],
        }
    )
    dataset["coverage"].update(
        {
            "medalsThroughLevel": MAX_LEVEL,
            "blueprintsThroughLevel": MAX_LEVEL,
            "contributorRewardsThroughLevel": MAX_LEVEL,
            "exactContributorRewardsThroughLevel": expanded["exactThroughTargetLevel"],
            "exactMedalTargetLevelRangesByEra": expanded.get(
                "medalExactTargetLevelRangesByEra", {}
            ),
            "exactFpTargetLevelRangesByEra": expanded.get(
                "fpExactTargetLevelRangesByEra", {}
            ),
            "estimatedContributorRewardsFromLevel": expanded["estimatedFromTargetLevel"],
        }
    )

    write_json(args.source, expanded)
    write_json(args.dataset, dataset)
    print(
        f"Expanded FP, medal, and blueprint contribution rewards through level {MAX_LEVEL} "
        f"in {args.source} and {args.dataset}"
    )


if __name__ == "__main__":
    main()
