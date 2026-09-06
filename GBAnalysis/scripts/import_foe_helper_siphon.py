#!/usr/bin/env python3
"""Merge Shattered Horizon Siphon contribution rewards into the source table.

Input is the JSON returned by FoE Helper's LegendaryBuilding/bulk endpoint for
X_StellarAgeDiscovery_Landmark1.  Only the unboosted P1 FP and medal values are
stored: GB Analysis derives the remaining FP/medal positions using the same
rounding rules and retains its independently validated five-position blueprint
table.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


BUILDING_ID = "X_StellarAgeDiscovery_Landmark1"
ERA_ID = "24"
SOURCE_URL = "https://api.foe-helper.com/v1/LegendaryBuilding/bulk"


def game_round(value: float) -> int:
    return math.floor(value + 0.500001)


def fp_positions(p1: int) -> list[int]:
    rewards = [p1]
    for position in range(2, 6):
        rewards.append(game_round(rewards[-1] / position / 5) * 5)
    return rewards


def medal_positions(p1: int) -> list[int]:
    return [
        p1,
        game_round(p1 / 2),
        game_round(p1 / 4),
        game_round(p1 / 10),
        game_round(p1 / 20),
    ]


def parse_response(payload: dict[str, Any], max_level: int = 201) -> dict[str, list[int]]:
    if payload.get("status") != 200 or not isinstance(payload.get("response"), list):
        raise ValueError("Expected a successful FoE Helper bulk response")

    rows: dict[int, dict[str, Any]] = {}
    for row in payload["response"]:
        if row.get("id") != BUILDING_ID:
            raise ValueError(f"Unexpected Great Building id: {row.get('id')!r}")
        level = row.get("level")
        if not isinstance(level, int) or level in rows:
            raise ValueError(f"Invalid or duplicate target level: {level!r}")
        rows[level] = row

    expected = set(range(1, max_level + 1))
    missing = sorted(expected - rows.keys())
    if missing:
        raise ValueError(f"FoE Helper response is missing target levels: {missing}")

    fp_p1: list[int] = []
    medal_p1: list[int] = []
    for level in range(1, max_level + 1):
        bonuses = rows[level].get("patron_bonus")
        if not isinstance(bonuses, list):
            raise ValueError(f"Target level {level} has no patron_bonus list")
        p1 = next((reward for reward in bonuses if reward.get("rank") == 1), None)
        if not p1:
            raise ValueError(f"Target level {level} has no P1 reward")
        values = [p1.get("forgepoints"), p1.get("medals")]
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError(f"Target level {level} has an invalid P1 reward")
        fp_p1.append(values[0])
        medal_p1.append(values[1])

    return {"fpP1": fp_p1, "medalP1": medal_p1}


def validate_position_rewards(
    payload: dict[str, Any], source: dict[str, Any], parsed: dict[str, list[int]]
) -> None:
    blueprints = source.get("blueprintsByLevel")
    if not isinstance(blueprints, list) or len(blueprints) < len(parsed["fpP1"]):
        raise ValueError("Contributor source has no complete blueprint table")

    for row in payload["response"]:
        level = row["level"]
        if level > len(parsed["fpP1"]):
            continue
        expected_fp = fp_positions(parsed["fpP1"][level - 1])
        expected_medals = medal_positions(parsed["medalP1"][level - 1])
        for reward in row["patron_bonus"]:
            rank = reward.get("rank")
            if not isinstance(rank, int) or not 1 <= rank <= 5:
                raise ValueError(f"Target level {level} has invalid rank {rank!r}")
            expected = (
                expected_fp[rank - 1],
                expected_medals[rank - 1],
                blueprints[level - 1][rank - 1],
            )
            actual = (
                reward.get("forgepoints", 0),
                reward.get("medals", 0),
                reward.get("blueprints", 0),
            )
            if actual != expected:
                raise ValueError(
                    f"Target level {level} P{rank} mismatch: {actual} != {expected}"
                )


def merge_siphon_rewards(
    source: dict[str, Any], payload: dict[str, Any], max_level: int = 201
) -> dict[str, Any]:
    parsed = parse_response(payload, max_level)
    validate_position_rewards(payload, source, parsed)

    source.setdefault("sourcePagesByEra", {})[ERA_ID] = BUILDING_ID
    source.setdefault("medalMaxTargetLevelByEra", {})[ERA_ID] = max_level
    source.setdefault("medalP1ByEra", {})[ERA_ID] = parsed["medalP1"]
    source.setdefault("validationFpP1ByEra", {})[ERA_ID] = parsed["fpP1"]
    source["additionalSources"] = {
        ERA_ID: {
            "source": SOURCE_URL,
            "buildingId": BUILDING_ID,
            "throughTargetLevel": max_level,
        }
    }
    return source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/contributor-rewards-source.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = json.loads(args.output.read_text(encoding="utf-8"))
    payload = json.loads(args.response.read_text(encoding="utf-8"))
    merged = merge_siphon_rewards(source, payload)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Merged Siphon rewards through level 201 into {args.output}")


if __name__ == "__main__":
    main()
