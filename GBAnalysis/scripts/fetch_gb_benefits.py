#!/usr/bin/env python3
"""Fetch per-level Great Building benefits through target level 301.

The long-running public tables at foe.kwister.net cover the 48 established
Great Buildings.  Shattered Horizon Siphon is sourced from the official live
wiki table through level 80; its documented post-level-10 supply progression
and fixed 5%-per-level combat progression are continued through level 301.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import math
import re
import time
import urllib.request
from pathlib import Path


MAX_LEVEL = 301
POWER_EXPONENT_BY_KEY = {
    "happiness": 0.5,
    "medals": 0.8,
    "money": 1.25,
    "population": 0.5,
    "supplies": 1.25,
}
BENEFIT_KEY_ALIASES = {"random_goods_afterModern": "random_goods_after_modern"}
KWISTER_BASE_URL = "https://foe.kwister.net/GB_list/{slug}?page={page}"
SIPHON_WIKI_URL = (
    "https://en.wiki.forgeofempires.com/"
    "index.php?title=Shattered_Horizon_Siphon"
)
NOTRE_DAME_WIKI_URL = "https://en.wiki.forgeofempires.com/index.php?title=Notre_Dame"

SOURCE_SLUGS = {
    "X_AllAge_EasterBonus4": "Observatory",
    "X_AllAge_Oracle": "OracleofDelphi",
    "X_AllAge_Expedition": "TempleofRelics",
    "X_BronzeAge_Landmark2": "StatueofZeus",
    "X_BronzeAge_Landmark1": "TowerofBabel",
    "X_IronAge_Landmark1": "Colosseum",
    "X_IronAge_Landmark2": "LighthouseofAlexandria",
    "X_EarlyMiddleAge_Landmark2": "CathedralofAachen",
    "X_EarlyMiddleAge_Landmark3": "GalataTower",
    "X_EarlyMiddleAge_Landmark1": "HagiaSophia",
    "X_HighMiddleAge_Landmark3": "NotreDame",
    "X_HighMiddleAge_Landmark1": "StMarksBasilica",
    "X_LateMiddleAge_Landmark3": "CasteldelMonte",
    "X_LateMiddleAge_Landmark1": "SaintBasilsCathedral",
    "X_ColonialAge_Landmark2": "DealCastle",
    "X_ColonialAge_Landmark1": "FrauenkircheofDresden",
    "X_IndustrialAge_Landmark2": "Capitol",
    "X_IndustrialAge_Landmark1": "RoyalAlbertHall",
    "X_ProgressiveEra_Landmark1": "Alcatraz",
    "X_ProgressiveEra_Landmark2": "ChateauFrontenac",
    "X_ModernEra_Landmark2": "Atomium",
    "X_ModernEra_Landmark1": "SpaceNeedle",
    "X_PostModernEra_Landmark1": "CapeCanaveral",
    "X_PostModernEra_Landmark2": "TheHabitat",
    "X_ContemporaryEra_Landmark2": "InnovationTower",
    "X_ContemporaryEra_Landmark1": "LotusTemple",
    "X_TomorrowEra_Landmark2": "TruceTower",
    "X_TomorrowEra_Landmark1": "VoyagerV1",
    "X_FutureEra_Landmark2": "RainForestProject",
    "X_FutureEra_Landmark1": "TheArc",
    "X_ArcticFuture_Landmark2": "ArcticOrangery",
    "X_ArcticFuture_Landmark1": "GaeaStatue",
    "X_ArcticFuture_Landmark3": "SeedVault",
    "X_OceanicFuture_Landmark1": "AtlantisMuseum",
    "X_OceanicFuture_Landmark3": "TheBlueGalaxy",
    "X_OceanicFuture_Landmark2": "TheKraken",
    "X_VirtualFuture_Landmark2": "HimejiCastle",
    "X_VirtualFuture_Landmark1": "TerracottaArmy",
    "X_SpaceAgeMars_Landmark1": "StarGazer",
    "X_SpaceAgeMars_Landmark2": "TheVirgoProject",
    "X_SpaceAgeAsteroidBelt_Landmark1": "SpaceCarrier",
    "X_SpaceAgeVenus_Landmark1": "FlyingIsland",
    "X_SpaceAgeJupiterMoon_Landmark1": "A.I.Core",
    "X_SpaceAgeTitan_Landmark1": "SaturnVIGateCENTAURUS",
    "X_SpaceAgeTitan_Landmark3": "SaturnVIGateHYDRA",
    "X_SpaceAgeTitan_Landmark2": "SaturnVIGatePEGASUS",
    "X_SpaceAgeSpaceHub_Landmark2": "CosmicCatalyst",
    "X_SpaceAgeSpaceHub_Landmark1": "StellarWarship",
}

DIRECTORY_SLUG_ALIASES = {
    "Colosseum": "Koloseum",
    "ChateauFrontenac": "ChteauFrontenac",
    "A.I.Core": "AICore",
}


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            )
        },
    )
    return urllib.request.urlopen(request, timeout=45).read().decode("utf-8")


def parse_number(source: str) -> int | float:
    normalized = html.unescape(source).strip().replace(",", "")
    value = float(normalized)
    return int(value) if value.is_integer() else value


def parse_benefit_items(segment: str) -> list[tuple[str, int | float]]:
    daily_rewards = segment.split("<!-- START GB REWARD TABLE -->", 1)[0]
    values = []
    for item in re.findall(r"<li>(.*?)</li>", daily_rewards, re.DOTALL):
        value_match = re.search(r"&nbsp;\(\s*([\d,.]+)\s*\)", item)
        if not value_match:
            continue
        key_match = re.search(r"title=['\"]([A-Za-z0-9_]+)['\"]", item)
        if not key_match:
            key_match = re.search(r"([A-Za-z0-9_]+)&nbsp;", item)
        if key_match:
            key = BENEFIT_KEY_ALIASES.get(key_match.group(1), key_match.group(1))
            values.append((key, parse_number(value_match.group(1))))
    return values


def extend_benefit_values(
    key: str, values: list[int | float]
) -> tuple[list[int | float], str | None]:
    if len(values) >= MAX_LEVEL:
        return values[:MAX_LEVEL], None
    if len(values) < 10:
        raise ValueError(f"Benefit {key} needs at least 10 source levels")

    exponent = POWER_EXPONENT_BY_KEY.get(key)
    if exponent is not None:
        level_ten_value = values[9]
        values.extend(
            math.ceil(level_ten_value * (level / 10) ** exponent)
            for level in range(len(values) + 1, MAX_LEVEL + 1)
        )
        return values, f"ceil(level-10 value * (target level / 10)^{exponent})"

    if len(values) >= 20 and len(set(values[-20:])) == 1:
        values.extend([values[-1]] * (MAX_LEVEL - len(values)))
        return values, "carry forward the source's capped value"

    sample_size = min(120, len(values) - 10)
    sample = values[-sample_size:]
    levels = list(range(len(values) - sample_size + 1, len(values) + 1))
    mean_level = sum(levels) / sample_size
    mean_value = sum(sample) / sample_size
    denominator = sum((level - mean_level) ** 2 for level in levels)
    slope = sum(
        (level - mean_level) * (value - mean_value)
        for level, value in zip(levels, sample)
    ) / denominator
    intercept = mean_value - slope * mean_level
    for level in range(len(values) + 1, MAX_LEVEL + 1):
        values.append(max(values[-1], round(intercept + slope * level)))
    return values, f"linear continuation of the latest {sample_size} source levels"


def repair_decreasing_source_values(values: list[int | float]) -> int:
    repaired = 0
    index = 0
    while index < len(values) - 1:
        if values[index] <= values[index + 1]:
            index += 1
            continue
        end = index + 1
        start = index
        while start > 0 and values[start - 1] > values[end]:
            start -= 1
        before_index = start - 1
        before = values[before_index] if before_index >= 0 else values[end]
        span = end - before_index
        for repair_index in range(start, end):
            position = repair_index - before_index
            values[repair_index] = round(
                before + (values[end] - before) * position / span
            )
            repaired += 1
        index = max(0, start - 1)
    return repaired


def parse_kwister_pages(pages: list[str]) -> tuple[list[dict[str, object]], dict[str, int]]:
    by_level: dict[int, list[tuple[str, int | float]]] = {}
    for page in pages:
        starts = list(re.finditer(r"<tr id=['\"](\d+)['\"]>", page))
        for index, start in enumerate(starts):
            level = int(start.group(1))
            end = starts[index + 1].start() if index + 1 < len(starts) else len(page)
            segment = page[start.start() : end]
            values = parse_benefit_items(segment)
            if values and any(value != 0 for _, value in values):
                by_level[level] = values

    if 1 not in by_level:
        raise ValueError("Benefit source is missing target level 1")
    keys = [key for key, _ in by_level[1]]
    for level, values in by_level.items():
        if [key for key, _ in values] != keys:
            raise ValueError(f"Benefit types changed at target level {level}")

    benefits = []
    extension_by_benefit = {}
    repaired_by_benefit = {}
    for key in keys:
        values = []
        current: int | float | None = None
        highest_level = max(by_level)
        for level in range(1, highest_level + 1):
            if level in by_level:
                candidate = dict(by_level[level])[key]
                if candidate != 0:
                    current = candidate
            if current is None:
                raise ValueError(f"Benefit {key} has no value at target level {level}")
            values.append(current)
        repaired = repair_decreasing_source_values(values)
        if repaired:
            repaired_by_benefit[key] = repaired
        values, extension = extend_benefit_values(key, values)
        if extension:
            extension_by_benefit[key] = extension
        benefits.append({"key": key, "values": values})
    return benefits, {
        "sourceTargetLevelCount": len(by_level),
        "highestSourceTargetLevel": max(by_level),
        "extensionByBenefit": extension_by_benefit,
        "repairedSourceValueCountByBenefit": repaired_by_benefit,
    }


def fetch_kwister_page(item: tuple[str, str, int]) -> tuple[str, int, str]:
    building_id, slug, page = item
    error: Exception | None = None
    for attempt in range(4):
        try:
            source = fetch_text(
                KWISTER_BASE_URL.format(slug=slug, page=page)
            )
            if not re.search(r"<tr id=['\"]\d+['\"]>", source):
                raise ValueError("response did not contain a level table")
            return building_id, page, source
        except Exception as caught:  # The source occasionally throttles.
            error = caught
            time.sleep(attempt + 1)
    raise RuntimeError(f"No usable benefit table for {slug}, page {page}: {error}")


def parse_siphon_wiki(source: str) -> list[dict[str, object]]:
    rows: dict[int, tuple[int, int]] = {}
    for row in re.findall(r"<tr>(.*?)</tr>", source, re.DOTALL):
        cells = [
            re.sub(r"<[^>]+>", "", cell).strip().replace(",", "")
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        ]
        if len(cells) != 5 or not cells[0].isdigit():
            continue
        rows[int(cells[0])] = (int(cells[3]), int(cells[4].rstrip("%")))

    if set(rows) != set(range(1, 81)):
        raise ValueError("Official Siphon table must contain levels 1 through 80")
    if any(rows[level][1] != level * 5 for level in rows):
        raise ValueError("Siphon combat progression no longer matches 5% per level")

    level_ten_supplies = rows[10][0]
    supplies = [rows[level][0] for level in range(1, 11)]
    supplies.extend(
        math.ceil(level_ten_supplies * (level / 10) ** 1.25)
        for level in range(11, MAX_LEVEL + 1)
    )
    for level in range(11, 81):
        if supplies[level - 1] != rows[level][0]:
            raise ValueError(f"Siphon supply formula disagrees at target level {level}")

    return [
        {"key": "supplies", "values": supplies},
        {"key": "advanced_tactics", "values": [level * 5 for level in range(1, MAX_LEVEL + 1)]},
    ]


def parse_notre_dame_wiki(source: str) -> list[dict[str, object]]:
    rows: dict[int, tuple[int, int]] = {}
    for row in re.findall(r"<tr>(.*?)</tr>", source, re.DOTALL):
        cells = [
            re.sub(r"<[^>]+>", "", cell).strip().replace(",", "")
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        ]
        if len(cells) == 5 and cells[0].isdigit():
            rows[int(cells[0])] = (int(cells[3]), int(cells[4]))
    if set(rows) != set(range(1, 81)):
        raise ValueError("Official Notre Dame table must contain levels 1 through 80")

    benefits = []
    for key, column, exponent in (("supplies", 0, 1.25), ("happiness", 1, 0.5)):
        level_ten_value = rows[10][column]
        values = [rows[level][column] for level in range(1, 11)]
        values.extend(
            math.ceil(level_ten_value * (level / 10) ** exponent)
            for level in range(11, MAX_LEVEL + 1)
        )
        for level in range(11, 81):
            if values[level - 1] != rows[level][column]:
                raise ValueError(
                    f"Notre Dame {key} formula disagrees at target level {level}"
                )
        benefits.append({"key": key, "values": values})
    return benefits


def build_source() -> dict[str, object]:
    directory_source = fetch_text("https://foe.kwister.net/GB_list/")
    highest_by_slug = {
        slug: int(level)
        for slug, level in re.findall(
            r"href=['\"]/GB_list/([^'\"]+)['\"]>.*?</a></div>\s*"
            r"<div[^>]*>(\d+)</div>",
            directory_source,
            re.DOTALL,
        )
    }
    missing_slugs = sorted(
        slug
        for slug in SOURCE_SLUGS.values()
        if DIRECTORY_SLUG_ALIASES.get(slug, slug) not in highest_by_slug
    )
    if missing_slugs:
        raise ValueError(f"GB source directory is missing slugs: {missing_slugs}")
    page_tasks = [
        (building_id, slug, page)
        for building_id, slug in SOURCE_SLUGS.items()
        if slug != "NotreDame"
        for page in range(
            min(3, (highest_by_slug[DIRECTORY_SLUG_ALIASES.get(slug, slug)] - 1) // 100)
            + 1
        )
    ]
    print(f"Fetching {len(page_tasks)} established-GB source pages", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        fetched_pages = list(executor.map(fetch_kwister_page, page_tasks))
    pages_by_building: dict[str, dict[int, str]] = {}
    for building_id, page, source in fetched_pages:
        pages_by_building.setdefault(building_id, {})[page] = source
    buildings = {}
    missing = []
    for building_id, slug in SOURCE_SLUGS.items():
        if slug == "NotreDame":
            continue
        try:
            benefits, coverage = parse_kwister_pages(
                [pages_by_building[building_id][page] for page in sorted(pages_by_building[building_id])]
            )
        except ValueError as error:
            print(f"Warning: no usable benefit table for {slug}: {error}", flush=True)
            missing.append(building_id)
            continue
        buildings[building_id] = {
            "source": KWISTER_BASE_URL.format(slug=slug, page="0-3"),
            "benefits": benefits,
            "coverage": coverage,
        }
    buildings["X_HighMiddleAge_Landmark3"] = {
        "source": NOTRE_DAME_WIKI_URL,
        "benefits": parse_notre_dame_wiki(fetch_text(NOTRE_DAME_WIKI_URL)),
        "extension": {
            "supplies": "ceil(level-10 value * (target level / 10)^1.25)",
            "happiness": "ceil(level-10 value * (target level / 10)^0.5)",
        },
    }
    buildings["X_StellarAgeDiscovery_Landmark1"] = {
        "source": SIPHON_WIKI_URL,
        "benefits": parse_siphon_wiki(fetch_text(SIPHON_WIKI_URL)),
        "extension": {
            "advanced_tactics": "5 * target level",
            "supplies": "ceil(level-10 value * (target level / 10)^1.25)",
        },
    }
    return {
        "schemaVersion": 1,
        "throughTargetLevel": MAX_LEVEL,
        "source": "https://foe.kwister.net/GB_list/",
        "additionalSources": {
            "notreDame": NOTRE_DAME_WIKI_URL,
            "shatteredHorizonSiphon": SIPHON_WIKI_URL,
        },
        "missingBuildingIds": missing,
        "buildings": buildings,
    }


def refresh_extensions(source: dict[str, object]) -> dict[str, object]:
    for building in source["buildings"].values():
        coverage = building.get("coverage")
        if not coverage:
            continue
        highest_level = coverage["highestSourceTargetLevel"]
        extension_by_benefit = {}
        repaired_by_benefit = {}
        for benefit in building["benefits"]:
            values = benefit["values"][:highest_level]
            repaired = repair_decreasing_source_values(values)
            if repaired:
                repaired_by_benefit[benefit["key"]] = repaired
            values, extension = extend_benefit_values(benefit["key"], values)
            benefit["values"] = values
            if extension:
                extension_by_benefit[benefit["key"]] = extension
        coverage["extensionByBenefit"] = extension_by_benefit
        coverage["repairedSourceValueCountByBenefit"] = repaired_by_benefit
        benefit_by_key = {benefit["key"]: benefit for benefit in building["benefits"]}
        if "random_goods" in benefit_by_key and "random_goods_after_modern" not in benefit_by_key:
            building["benefits"].append(
                {
                    "key": "random_goods_after_modern",
                    "values": [value * 2 for value in benefit_by_key["random_goods"]["values"]],
                }
            )
            coverage["derivedBenefits"] = {
                "random_goods_after_modern": "2 * random_goods"
            }
    return source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/gb-benefits-source.json"),
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reapply extension formulas to an already fetched complete source file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = (
        refresh_extensions(json.loads(args.output.read_text(encoding="utf-8")))
        if args.reuse_existing
        else build_source()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(source['buildings'])} benefit tables to {args.output}")


if __name__ == "__main__":
    main()
