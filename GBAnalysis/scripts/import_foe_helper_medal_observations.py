#!/usr/bin/env python3
"""Normalize later-level medal observations from FoE Helper API responses.

Pass one or more saved ``LegendaryBuilding/bulk`` JSON responses.  The importer
keeps only target levels above the base table's exact cutoff, validates P2-P5
against the game's P1 fractions, rejects duplicated-neighbor API anomalies, and
resolves remaining conflicts against the checked fallback curve.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from build_dataset import (
    ERA_IDS,
    MEDAL_REWARD_EXPONENT,
    game_round,
    least_squares_scale,
    medal_position_rewards,
)


SOURCE_URL = "https://api.foe-helper.com/v1/LegendaryBuilding/bulk"
API_ERA_IDS = {**ERA_IDS, "AllAge": 0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", type=Path, nargs="+")
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
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/contributor-medal-observations.json"),
    )
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    return parser.parse_args()


def valid_rows(payload: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    if payload.get("status") != 200 or not isinstance(payload.get("response"), list):
        raise ValueError(f"{path}: expected a successful FoE Helper bulk response")
    rows = [row for row in payload["response"] if isinstance(row, dict)]
    return sorted(rows, key=lambda row: row.get("level", -1))


def has_bad_neighbor(rows: list[dict[str, Any]], index: int, p1_medals: int) -> bool:
    row = rows[index]
    level = row["level"]
    if index > 0:
        previous = rows[index - 1]
        if (
            previous.get("level") == level - 1
            and previous.get("patron_bonus")
            and previous["patron_bonus"][0].get("medals", -1) >= p1_medals
        ):
            return True
    if index + 1 < len(rows):
        following = rows[index + 1]
        if (
            following.get("level") == level + 1
            and following.get("patron_bonus")
            and following["patron_bonus"][0].get("medals", p1_medals + 1) <= p1_medals
        ):
            return True
    return False


def collect_candidates(
    response_paths: list[Path],
    source: dict[str, Any],
    building_eras: dict[str, int],
) -> tuple[dict[str, dict[int, list[int]]], int]:
    exact_through = int(source.get("exactThroughTargetLevel", 201))
    base_medals = source["medalP1ByEra"]
    candidates: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    rejected = 0

    for path in response_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = valid_rows(payload, path)
        for index, row in enumerate(rows):
            era_name = row.get("era")
            era_number = building_eras.get(row.get("id"), API_ERA_IDS.get(era_name))
            if era_number is None:
                raise ValueError(f"{path}: unknown era {era_name!r}")
            era_id = str(era_number)
            level = row.get("level")
            bonuses = row.get("patron_bonus")
            if not isinstance(level, int) or not isinstance(bonuses, list):
                rejected += 1
                continue
            by_rank = {
                reward.get("rank"): reward
                for reward in bonuses
                if isinstance(reward, dict) and isinstance(reward.get("rank"), int)
            }
            p1 = by_rank.get(1, {}).get("medals")
            if not isinstance(p1, int) or p1 < 0:
                rejected += 1
                continue
            if level <= exact_through:
                if base_medals[era_id][level - 1] != p1:
                    rejected += 1
                continue
            expected = medal_position_rewards(p1)
            for rank, expected_value in enumerate(expected, start=1):
                if by_rank.get(rank, {}).get("medals", 0) != expected_value:
                    raise ValueError(
                        f"{path}: target level {level} P{rank} medal mismatch"
                    )

            if has_bad_neighbor(rows, index, p1):
                rejected += 1
                continue
            candidates[era_id][level].append(p1)

    return candidates, rejected


def fallback_value(base_values: list[int], level: int) -> int:
    scale = least_squares_scale(
        base_values,
        MEDAL_REWARD_EXPONENT,
        subtract_one=True,
    )
    return game_round(scale * (level**MEDAL_REWARD_EXPONENT - 1))


def resolve_candidates(
    candidates: dict[str, dict[int, list[int]]],
    source: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], int]:
    exact_through = int(source.get("exactThroughTargetLevel", 201))
    output: dict[str, dict[str, int]] = {}
    conflict_count = 0
    for era_id, levels in sorted(candidates.items(), key=lambda item: int(item[0])):
        output[era_id] = {}
        base_values = source["medalP1ByEra"][era_id][:exact_through]
        for level, values in sorted(levels.items()):
            counts = Counter(values)
            highest_count = max(counts.values())
            choices = [value for value, count in counts.items() if count == highest_count]
            if len(counts) > 1:
                conflict_count += 1
            if len(choices) > 1:
                modeled = fallback_value(base_values, level)
                choices.sort(key=lambda value: abs(value - modeled))
            output[era_id][str(level)] = choices[0]
    return output, conflict_count


def main() -> None:
    args = parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    building_eras = {
        building["id"]: building["eraId"] for building in dataset["buildings"]
    }
    candidates, rejected = collect_candidates(args.responses, source, building_eras)
    observations, conflicts = resolve_candidates(candidates, source)
    payload = {
        "source": SOURCE_URL,
        "retrievedOn": args.retrieved_on,
        "medalP1ByEra": observations,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    count = sum(len(levels) for levels in observations.values())
    print(
        f"Wrote {count} exact later-level medal observations to {args.output}; "
        f"rejected {rejected} anomalous rows and resolved {conflicts} conflicts"
    )


if __name__ == "__main__":
    main()
