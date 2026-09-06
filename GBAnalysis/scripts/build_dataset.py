#!/usr/bin/env python3
"""Build the self-contained GB Analysis dataset from FoE Helper and CityEntities."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
from pathlib import Path
from typing import Any


ERA_IDS = {
    "NoAge": 0,
    "StoneAge": 1,
    "BronzeAge": 2,
    "IronAge": 3,
    "EarlyMiddleAge": 4,
    "HighMiddleAge": 5,
    "LateMiddleAge": 6,
    "ColonialAge": 7,
    "IndustrialAge": 8,
    "ProgressiveEra": 9,
    "ModernEra": 10,
    "PostModernEra": 11,
    "ContemporaryEra": 12,
    "TomorrowEra": 13,
    "FutureEra": 14,
    "ArcticFuture": 15,
    "OceanicFuture": 16,
    "VirtualFuture": 17,
    "SpaceAgeMars": 18,
    "SpaceAgeAsteroidBelt": 19,
    "SpaceAgeVenus": 20,
    "SpaceAgeJupiterMoon": 21,
    "SpaceAgeTitan": 22,
    "SpaceAgeSpaceHub": 23,
    "StellarAgeDiscovery": 24,
}

ERA_NAMES = {
    "NoAge": "No Age / All Ages",
    "StoneAge": "Stone Age",
    "BronzeAge": "Bronze Age",
    "IronAge": "Iron Age",
    "EarlyMiddleAge": "Early Middle Ages",
    "HighMiddleAge": "High Middle Ages",
    "LateMiddleAge": "Late Middle Ages",
    "ColonialAge": "Colonial Age",
    "IndustrialAge": "Industrial Age",
    "ProgressiveEra": "Progressive Era",
    "ModernEra": "Modern Era",
    "PostModernEra": "Postmodern Era",
    "ContemporaryEra": "Contemporary Era",
    "TomorrowEra": "Tomorrow Era",
    "FutureEra": "Future Era",
    "ArcticFuture": "Arctic Future",
    "OceanicFuture": "Oceanic Future",
    "VirtualFuture": "Virtual Future",
    "SpaceAgeMars": "Space Age Mars",
    "SpaceAgeAsteroidBelt": "Space Age Asteroid Belt",
    "SpaceAgeVenus": "Space Age Venus",
    "SpaceAgeJupiterMoon": "Space Age Jupiter Moon",
    "SpaceAgeTitan": "Space Age Titan",
    "SpaceAgeSpaceHub": "Space Age Space Hub",
    "StellarAgeDiscovery": "Stellar Age: Discovery",
}

MAX_LEVEL = 301
EXACT_REWARD_MAX_LEVEL = 201
REWARD_MAX_LEVEL = MAX_LEVEL
FP_REWARD_EXPONENT = 1.2
# This is only the fallback for later levels absent from the exact FoE Helper
# observation table.  It minimizes absolute P1 error across all 1,965 available
# API observations above level 201; observed values always take precedence.
MEDAL_REWARD_EXPONENT = 1.200964
BLUEPRINT_REWARD_EXPONENT = 0.8
MEDAL_OBSERVATIONS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "contributor-medal-observations.json"
)

# The public table has an isolated blank Future Era medal cell at target level
# 196.  FoE Helper's LegendaryBuilding API reports the value below, between
# 102,262 at level 195 and 103,510 at level 197.
MEDAL_SOURCE_CORRECTIONS = {("14", 196): 102_874}

# Sanitized reward-only facts from direct GreatBuildingsService.getConstruction
# responses.  The raw captures contain player data and intentionally remain
# outside the generated dataset and version control.
DIRECT_REWARD_CAPTURES = (
    {
        "buildingId": "X_ProgressiveEra_Landmark2",
        "eraId": 9,
        "targetLevel": 248,
        "forgePoints": [4_195, 2_100, 700, 175, 35],
        "medals": [36_124, 18_062, 9_031, 3_612, 1_806],
        "blueprints": [38, 27, 21, 17, 15],
    },
    {
        "buildingId": "X_FutureEra_Landmark1",
        "eraId": 14,
        "targetLevel": 214,
        "forgePoints": [4_490, 2_245, 750, 190, 40],
        "medals": [114_335, 57_168, 28_584, 11_434, 5_717],
        "blueprints": [34, 24, 19, 15, 13],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 234,
        "medals": [192_368, 96_184],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 235,
        "medals": [193_360, 96_680],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 236,
        "medals": [194_387, 97_194],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 237,
        "medals": [195_343, 97_672],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 238,
        "medals": [196_334, 98_167],
    },
    {
        "buildingId": "X_OceanicFuture_Landmark2",
        "eraId": 16,
        "targetLevel": 239,
        "forgePoints": [5_575, 2_790, 930, 235, 45],
        "medals": [197_325, 98_663, 49_331, 19_733, 9_866],
        "blueprints": [37, 26, 20, 17, 14],
    },
)


# A full blueprint set unlocks every target level from 11 onward. These formulas
# describe the additional resources required by the six newest Great Buildings.
# Each step is target_level - 10, so (for example) level 12 costs twice level 11.
LEVEL_UNLOCK_FORMULAS = {
    "X_SpaceAgeTitan_Landmark1": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 80,
        "resourcesPerStep": {"money": 4_000_000},
    },
    "X_SpaceAgeTitan_Landmark2": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 60,
        "resourcesPerStep": {"money": 3_000_000},
    },
    "X_SpaceAgeTitan_Landmark3": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 100,
        "resourcesPerStep": {"money": 5_000_000},
    },
    "X_SpaceAgeSpaceHub_Landmark1": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 125,
        "resourcesPerStep": {"supplies": 4_000_000},
    },
    "X_SpaceAgeSpaceHub_Landmark2": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 150,
        "resourcesPerStep": {"dark_matter": 100},
    },
    "X_StellarAgeDiscovery_Landmark1": {
        "startLevel": 11,
        "blueprintSets": 1,
        "goodsPerTypePerStep": 275,
        "resourcesPerStep": {"money": 97_200, "supplies": 97_200, "medals": 97_200},
    },
}


def extract_balanced_object(source: str, marker: str) -> str:
    marker_at = source.find(marker)
    if marker_at < 0:
        raise ValueError(f"Could not find {marker!r}")
    start = source.find("{", marker_at)
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index]
    raise ValueError(f"Unclosed object after {marker!r}")


def extract_reward_tables(source: str) -> dict[int, list[int]]:
    reward_block = extract_balanced_object(source, "Rewards:")
    matches = re.finditer(r"(?m)^\s*(\d+)\s*:\s*\[([\d,\s]+)\]\s*,?", reward_block)
    tables: dict[int, list[int]] = {}
    for match in matches:
        era_id = int(match.group(1))
        values = [int(value) for value in match.group(2).split(",") if value.strip()]
        if not values:
            raise ValueError(f"Empty reward table for era {era_id}")
        tables[era_id] = values

    required = {0, *range(2, 25)}
    missing = sorted(required - tables.keys())
    if missing:
        raise ValueError(f"Forge Hammer reward tables missing eras: {missing}")
    return tables


def find_extension_version(source_path: Path) -> str:
    for parent in source_path.parents:
        manifest = parent / "manifest.json"
        if manifest.is_file():
            value = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            if value:
                return str(value)
    return "unknown"


def positive_foundation_resources(entity: dict[str, Any]) -> dict[str, int | float]:
    resources = entity.get("requirements", {}).get("cost", {}).get("resources", {})
    return {key: value for key, value in resources.items() if isinstance(value, (int, float)) and value > 0}


def game_round(value: float) -> int:
    return math.floor(value + 0.500001)


def fp_reward_estimate(era_id: int, target_level: int) -> int:
    era_factor = 14 if era_id == 0 else era_id + 9
    raw = era_factor * (target_level**FP_REWARD_EXPONENT - 1) / 3.2
    return game_round(raw / 5) * 5


def fp_position_rewards(p1_reward: int) -> list[int]:
    rewards = [p1_reward]
    for position in range(2, 6):
        rewards.append(game_round(rewards[-1] / position / 5) * 5)
    return rewards


def medal_position_rewards(p1_reward: int) -> list[int]:
    return [
        p1_reward,
        game_round(p1_reward / 2),
        game_round(p1_reward / 4),
        game_round(p1_reward / 10),
        game_round(p1_reward / 20),
    ]


def compress_level_ranges(levels: set[int]) -> list[list[int]]:
    """Return sorted integer levels as compact inclusive ranges."""

    if not levels:
        return []
    ordered = sorted(levels)
    ranges: list[list[int]] = []
    start = previous = ordered[0]
    for level in ordered[1:]:
        if level == previous + 1:
            previous = level
            continue
        ranges.append([start, previous])
        start = previous = level
    ranges.append([start, previous])
    return ranges


def load_medal_observations(path: Path = MEDAL_OBSERVATIONS_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("medalP1ByEra"), dict):
        raise ValueError("Medal observation source is missing medalP1ByEra")
    return payload


def least_squares_scale(
    values: list[int], exponent: float, *, subtract_one: bool
) -> float:
    numerator = 0.0
    denominator = 0.0
    for target_level, value in enumerate(values, start=1):
        if value <= 0:
            continue
        curve = target_level**exponent - (1 if subtract_one else 0)
        numerator += curve * value
        denominator += curve * curve
    if denominator == 0:
        raise ValueError("Cannot fit a reward curve without positive source values")
    return numerator / denominator


def _rolling_backtest(
    values_by_series: dict[str, list[int]],
    exponent: float,
    *,
    subtract_one: bool,
) -> dict[str, int | float]:
    errors: list[int] = []
    relative_errors: list[float] = []
    for cutoff in (100, 120, 140, 160, 180):
        training_start = max(1, cutoff - 79)
        for values in values_by_series.values():
            numerator = 0.0
            denominator = 0.0
            for target_level in range(training_start, cutoff + 1):
                value = values[target_level - 1]
                if value <= 0:
                    continue
                curve = target_level**exponent - (1 if subtract_one else 0)
                numerator += curve * value
                denominator += curve * curve
            scale = numerator / denominator
            for target_level in range(cutoff + 1, min(EXACT_REWARD_MAX_LEVEL, cutoff + 40) + 1):
                actual = values[target_level - 1]
                if actual <= 0:
                    continue
                curve = target_level**exponent - (1 if subtract_one else 0)
                error = game_round(scale * curve) - actual
                errors.append(abs(error))
                relative_errors.append(abs(error) / actual)
    return {
        "comparisonCount": len(errors),
        "meanAbsoluteError": round(sum(errors) / len(errors), 6),
        "maximumAbsoluteError": max(errors),
        "meanAbsolutePercentageError": round(
            100 * sum(relative_errors) / len(relative_errors), 6
        ),
        "maximumAbsolutePercentageError": round(100 * max(relative_errors), 6),
    }


def expand_contributor_rewards(
    source: dict[str, Any],
    fp_source_by_era: dict[int, list[int]],
    max_level: int = MAX_LEVEL,
) -> dict[str, Any]:
    """Preserve sourced rewards through 201 and model target levels 202-301."""

    expanded = copy.deepcopy(source)
    exact_level = int(expanded.get("exactThroughTargetLevel", EXACT_REWARD_MAX_LEVEL))
    if exact_level != EXACT_REWARD_MAX_LEVEL:
        raise ValueError(
            f"Contributor source must retain exact rewards through level {EXACT_REWARD_MAX_LEVEL}"
        )

    medals = expanded.get("medalP1ByEra")
    blueprints = expanded.get("blueprintsByLevel")
    if not isinstance(medals, dict):
        raise ValueError("Contributor reward source is missing medalP1ByEra")
    if not isinstance(blueprints, list) or len(blueprints) < exact_level:
        raise ValueError(f"Expected at least {exact_level} blueprint reward rows")

    exact_medals: dict[str, list[int]] = {}
    for era_id, values in medals.items():
        if not isinstance(values, list) or len(values) < exact_level:
            raise ValueError(f"Invalid medal P1 table for era {era_id}")
        exact_values = values[:exact_level]
        if any(not isinstance(value, int) or value < 0 for value in exact_values):
            raise ValueError(f"Invalid medal P1 table for era {era_id}")
        exact_medals[era_id] = exact_values

    for (era_id, target_level), value in MEDAL_SOURCE_CORRECTIONS.items():
        if era_id in exact_medals and exact_medals[era_id][target_level - 1] == 0:
            exact_medals[era_id][target_level - 1] = value

    exact_blueprints = blueprints[:exact_level]
    if any(
        not isinstance(row, list)
        or len(row) != 5
        or any(not isinstance(value, int) or value < 0 for value in row)
        for row in exact_blueprints
    ):
        raise ValueError("Each blueprint reward row must contain five non-negative integers")

    full_fp: dict[str, list[int]] = {}
    for era_id, source_values in fp_source_by_era.items():
        if len(source_values) < exact_level:
            raise ValueError(
                f"FP reward source for era {era_id} ends before level {exact_level}"
            )
        values = list(source_values[:exact_level])
        values.extend(
            fp_reward_estimate(era_id, target_level)
            for target_level in range(exact_level + 1, max_level + 1)
        )
        full_fp[str(era_id)] = values

    medal_scales: dict[str, float] = {}
    full_medals: dict[str, list[int]] = {}
    for era_id, exact_values in exact_medals.items():
        scale = least_squares_scale(
            exact_values,
            MEDAL_REWARD_EXPONENT,
            subtract_one=True,
        )
        medal_scales[era_id] = scale
        values = list(exact_values)
        values.extend(
            game_round(scale * (target_level**MEDAL_REWARD_EXPONENT - 1))
            for target_level in range(exact_level + 1, max_level + 1)
        )
        full_medals[era_id] = values

    # The medal curve contains discrete game-table steps that a smooth power
    # function cannot reproduce exactly (Kraken level 236 is one example).
    # Overlay every later-level value available from FoE Helper's public API
    # and retain the fitted curve only for genuinely unobserved cells.
    observation_source = load_medal_observations()
    observed_medals: dict[str, dict[int, int]] = {}
    fallback_observation_errors: list[int] = []
    for era_id, level_values in observation_source["medalP1ByEra"].items():
        if era_id not in full_medals:
            raise ValueError(f"Medal observations reference unavailable era {era_id}")
        if not isinstance(level_values, dict):
            raise ValueError(f"Invalid medal observation table for era {era_id}")
        observed_medals[era_id] = {}
        for level_text, value in level_values.items():
            try:
                target_level = int(level_text)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid medal observation level {level_text!r} for era {era_id}"
                ) from error
            if (
                target_level <= exact_level
                or target_level > max_level
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"Invalid medal observation for era {era_id}, "
                    f"target level {target_level}: {value!r}"
                )
            index = target_level - 1
            fallback_observation_errors.append(full_medals[era_id][index] - value)
            full_medals[era_id][index] = value
            observed_medals[era_id][target_level] = value

    exact_medal_levels: dict[str, set[int]] = {
        era_id: set(range(1, exact_level + 1)) | set(observed_medals.get(era_id, {}))
        for era_id in full_medals
    }
    exact_medal_ranges = {
        era_id: compress_level_ranges(levels)
        for era_id, levels in exact_medal_levels.items()
    }
    exact_medal_max: dict[str, int] = {}
    for era_id, levels in exact_medal_levels.items():
        contiguous_max = 0
        while contiguous_max + 1 in levels:
            contiguous_max += 1
        exact_medal_max[era_id] = contiguous_max

    blueprint_scales = []
    for position in range(5):
        position_values = [row[position] for row in exact_blueprints]
        blueprint_scales.append(
            least_squares_scale(
                position_values,
                BLUEPRINT_REWARD_EXPONENT,
                subtract_one=False,
            )
        )
    full_blueprints = copy.deepcopy(exact_blueprints)
    for target_level in range(exact_level + 1, max_level + 1):
        full_blueprints.append(
            [
                game_round(scale * target_level**BLUEPRINT_REWARD_EXPONENT)
                for scale in blueprint_scales
            ]
        )

    direct_capture_errors = []
    applied_captures = []
    for capture in DIRECT_REWARD_CAPTURES:
        target_level = capture["targetLevel"]
        if target_level > max_level:
            continue
        era_id = str(capture["eraId"])
        index = target_level - 1
        if era_id not in full_fp or era_id not in full_medals:
            raise ValueError(f"Direct capture references unavailable reward era {era_id}")
        if "forgePoints" in capture and fp_position_rewards(
            full_fp[era_id][index]
        ) != capture["forgePoints"]:
            raise ValueError(
                f"FP formula does not match direct capture for era {era_id}, "
                f"target level {target_level}"
            )
        captured_medals = capture["medals"]
        if (
            medal_position_rewards(captured_medals[0])[: len(captured_medals)]
            != captured_medals
        ):
            raise ValueError(
                f"Medal fractions do not match direct capture for era {era_id}, "
                f"target level {target_level}"
            )

        modeled_medal = game_round(
            medal_scales[era_id]
            * (target_level**MEDAL_REWARD_EXPONENT - 1)
        )
        direct_capture_errors.append(modeled_medal - captured_medals[0])

        if (
            target_level in exact_medal_levels[era_id]
            and full_medals[era_id][index] != captured_medals[0]
        ):
            raise ValueError(
                f"Exact medal sources disagree for era {era_id}, "
                f"target level {target_level}"
            )

        # Direct game values take precedence over a curve estimate at captured
        # levels.  Where FP and blueprints are present they are assigned too, so
        # these sparse exact rows remain explicit and regression-tested.
        if "forgePoints" in capture:
            full_fp[era_id][index] = capture["forgePoints"][0]
        full_medals[era_id][index] = captured_medals[0]
        if "blueprints" in capture:
            full_blueprints[index] = list(capture["blueprints"])
        applied_captures.append(copy.deepcopy(capture))

    fp_errors = []
    for era_id, values in fp_source_by_era.items():
        for target_level in range(11, exact_level + 1):
            fp_errors.append(
                abs(fp_reward_estimate(era_id, target_level) - values[target_level - 1])
            )
    blueprint_series = {
        str(position + 1): [row[position] for row in exact_blueprints]
        for position in range(5)
    }

    expanded.update(
        {
            "throughTargetLevel": max_level,
            "exactThroughTargetLevel": exact_level,
            "estimatedFromTargetLevel": exact_level + 1,
            "medalExactMaxTargetLevelByEra": exact_medal_max,
            "medalExactTargetLevelRangesByEra": exact_medal_ranges,
            "medalMaxTargetLevelByEra": {
                era_id: max_level for era_id in full_medals
            },
            "fpP1ByEra": full_fp,
            "medalP1ByEra": full_medals,
            "blueprintsByLevel": full_blueprints,
            "estimation": {
                "basis": "Sourced rows through level 201 and all available later FoE Helper API observations are preserved exactly. Curves are used only for reward cells without an observation.",
                "fpP1": {
                    "formula": "round-to-nearest-5(eraFactor * (level^1.2 - 1) / 3.2), where eraFactor is eraId + 9 and No Age uses 14",
                    "exponent": FP_REWARD_EXPONENT,
                    "backtest": {
                        "comparisonCount": len(fp_errors),
                        "exactPercentage": round(
                            100 * sum(error == 0 for error in fp_errors) / len(fp_errors), 6
                        ),
                        "withinFivePercentage": round(
                            100 * sum(error <= 5 for error in fp_errors) / len(fp_errors), 6
                        ),
                        "maximumAbsoluteError": max(fp_errors),
                    },
                },
                "medalP1": {
                    "formula": f"fallback only: round(eraScale * (level^{MEDAL_REWARD_EXPONENT} - 1)); exact table observations take precedence",
                    "exponent": MEDAL_REWARD_EXPONENT,
                    "scaleByEra": {
                        era_id: round(scale, 12) for era_id, scale in medal_scales.items()
                    },
                    "rollingBacktest": _rolling_backtest(
                        exact_medals,
                        MEDAL_REWARD_EXPONENT,
                        subtract_one=True,
                    ),
                    "directCaptureValidationBeforeExactOverrides": {
                        "comparisonCount": len(direct_capture_errors),
                        "meanAbsoluteError": round(
                            sum(abs(error) for error in direct_capture_errors)
                            / len(direct_capture_errors),
                            6,
                        ),
                        "maximumAbsoluteError": max(
                            abs(error) for error in direct_capture_errors
                        ),
                        "signedErrors": direct_capture_errors,
                    },
                    "fallbackValidationAgainstLaterObservations": {
                        "comparisonCount": len(fallback_observation_errors),
                        "meanAbsoluteError": round(
                            sum(abs(error) for error in fallback_observation_errors)
                            / len(fallback_observation_errors),
                            6,
                        ),
                        "maximumAbsoluteError": max(
                            abs(error) for error in fallback_observation_errors
                        ),
                        "exactPercentage": round(
                            100
                            * sum(error == 0 for error in fallback_observation_errors)
                            / len(fallback_observation_errors),
                            6,
                        ),
                    },
                },
                "blueprints": {
                    "formula": "round(positionScale * level^0.8); each position scale is a least-squares fit to sourced values",
                    "exponent": BLUEPRINT_REWARD_EXPONENT,
                    "scaleByPosition": [round(scale, 12) for scale in blueprint_scales],
                    "rollingBacktest": _rolling_backtest(
                        blueprint_series,
                        BLUEPRINT_REWARD_EXPONENT,
                        subtract_one=False,
                    ),
                },
            },
            "directCapturedRewards": applied_captures,
            "medalObservations": {
                "source": observation_source.get("source"),
                "retrievedOn": observation_source.get("retrievedOn"),
                "comparisonCount": sum(
                    len(level_values) for level_values in observed_medals.values()
                ),
                "exactTargetLevelRangesByEra": exact_medal_ranges,
            },
            "sourceCorrections": {
                "medalP1ByEra.14.targetLevel196": {
                    "value": 102_874,
                    "source": "https://api.foe-helper.com/v1/LegendaryBuilding/bulk",
                    "buildingId": "X_FutureEra_Landmark2",
                }
            },
        }
    )
    return expanded


def load_contributor_rewards(source_path: Path) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    return source


def build_dataset(
    forge_hammer_source: Path,
    city_entities_source: Path,
    contributor_rewards_source: Path,
) -> dict[str, Any]:
    reward_tables = extract_reward_tables(forge_hammer_source.read_text(encoding="utf-8"))
    contributor_source = load_contributor_rewards(contributor_rewards_source)
    for era_id, values in contributor_source.get("validationFpP1ByEra", {}).items():
        forge_hammer_values = reward_tables.get(int(era_id), [])
        for index, source_value in enumerate(values[: len(forge_hammer_values)]):
            if source_value in (None, 0):
                continue
            if source_value != forge_hammer_values[index]:
                raise ValueError(
                    f"Contributor source FP mismatch for era {era_id}, "
                    f"target level {index + 1}"
                )
    raw_entities = json.loads(city_entities_source.read_text(encoding="utf-8"))
    if isinstance(raw_entities, dict):
        entities_container = raw_entities.get("CityEntities", raw_entities)
        entities = entities_container.values()
    else:
        entities = raw_entities

    buildings = []
    for entity in entities:
        if entity.get("type") != "greatbuilding":
            continue
        era = entity.get("requirements", {}).get("min_era")
        if era not in ERA_IDS:
            raise ValueError(f"Unknown era {era!r} for {entity.get('id')}")
        first_ten = entity.get("strategy_points_for_upgrade")
        if not isinstance(first_ten, list) or len(first_ten) != 10:
            raise ValueError(f"Expected 10 seed costs for {entity.get('id')}")
        if ERA_IDS[era] not in reward_tables:
            raise ValueError(f"No Forge Hammer reward table for era {era}")

        building = {
            "id": entity["id"],
            "name": entity["name"],
            "era": era,
            "eraId": ERA_IDS[era],
            "width": entity.get("width"),
            "length": entity.get("length"),
            "foundationGoods": positive_foundation_resources(entity),
            "firstTenLevelCosts": first_ten,
        }
        if entity["id"] in LEVEL_UNLOCK_FORMULAS:
            building["levelUnlockFormula"] = LEVEL_UNLOCK_FORMULAS[entity["id"]]
        buildings.append(building)

    missing_unlock_buildings = sorted(
        set(LEVEL_UNLOCK_FORMULAS) - {building["id"] for building in buildings}
    )
    if missing_unlock_buildings:
        raise ValueError(f"Level unlock formulas reference missing GBs: {missing_unlock_buildings}")

    contributor_rewards = expand_contributor_rewards(
        contributor_source,
        reward_tables,
        REWARD_MAX_LEVEL,
    )
    buildings.sort(key=lambda item: (item["eraId"], item["name"]))
    used_era_ids = sorted({building["eraId"] for building in buildings})
    missing_medal_eras = [
        era_id for era_id in used_era_ids if str(era_id) not in contributor_rewards["medalP1ByEra"]
    ]
    if missing_medal_eras:
        raise ValueError(f"Contributor reward source missing medal eras: {missing_medal_eras}")
    incomplete = {
        str(era_id): len(contributor_rewards["fpP1ByEra"][str(era_id)])
        for era_id in used_era_ids
        if len(contributor_rewards["fpP1ByEra"][str(era_id)]) < REWARD_MAX_LEVEL
    }

    return {
        "schemaVersion": 3,
        "maxLevel": MAX_LEVEL,
        "sources": {
            "forgeHammer": {
                "version": find_extension_version(forge_hammer_source),
                "sourceFile": "js/web/greatbuildings/js/greatbuildings.js",
            },
            "cityEntities": {"sourceFile": city_entities_source.name},
            "contributorRewards": {
                "sourceFile": contributor_rewards_source.name,
                "source": contributor_rewards["source"],
                "additionalSources": contributor_rewards.get("additionalSources", {}),
                "throughTargetLevel": contributor_rewards["throughTargetLevel"],
                "exactThroughTargetLevel": contributor_rewards["exactThroughTargetLevel"],
                "estimatedFromTargetLevel": contributor_rewards["estimatedFromTargetLevel"],
                "estimation": contributor_rewards["estimation"],
                "medalObservations": contributor_rewards.get("medalObservations", {}),
                "directCapturedRewards": contributor_rewards.get(
                    "directCapturedRewards", []
                ),
            },
            "levelUnlockCosts": {
                "throughTargetLevel": MAX_LEVEL,
                "source": "game unlock-cost tables cross-checked against public GB level tables",
            },
        },
        "coverage": {
            "buildingCount": len(buildings),
            "upgradeCostsThroughLevel": MAX_LEVEL,
            "medalsThroughLevel": contributor_rewards["throughTargetLevel"],
            "blueprintsThroughLevel": contributor_rewards["throughTargetLevel"],
            "contributorRewardsThroughLevel": contributor_rewards["throughTargetLevel"],
            "exactContributorRewardsThroughLevel": contributor_rewards[
                "exactThroughTargetLevel"
            ],
            "exactMedalTargetLevelRangesByEra": contributor_rewards.get(
                "medalExactTargetLevelRangesByEra", {}
            ),
            "estimatedContributorRewardsFromLevel": contributor_rewards[
                "estimatedFromTargetLevel"
            ],
            "levelUnlockCostsThroughLevel": MAX_LEVEL,
            "incompleteRewardEraMaxLevels": incomplete,
        },
        "eraNames": {str(ERA_IDS[key]): value for key, value in ERA_NAMES.items()},
        "rewardP1ByEra": {
            str(key): contributor_rewards["fpP1ByEra"][str(key)]
            for key in sorted(reward_tables)
        },
        "medalP1ByEra": contributor_rewards["medalP1ByEra"],
        "blueprintsByLevel": contributor_rewards["blueprintsByLevel"],
        "buildings": buildings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-hammer-source", type=Path, required=True)
    parser.add_argument("--city-entities", type=Path, required=True)
    parser.add_argument("--contributor-rewards", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/gb-analysis.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset(
        args.forge_hammer_source,
        args.city_entities,
        args.contributor_rewards,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(dataset['buildings'])} Great Buildings and "
        f"{len(dataset['rewardP1ByEra'])} era reward tables to {args.output}"
    )


if __name__ == "__main__":
    main()
