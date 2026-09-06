#!/usr/bin/env python3
"""Fetch and normalize the base GB medal/blueprint tables through level 201.

The Forge Hammer extension reads these values from live
GreatBuildingsService.getConstruction responses; it does not carry an offline
medal or blueprint table.  This script uses the public, unboosted tables at
foe.kwister.net for eras through Space Age: Space Hub.  Run
import_foe_helper_siphon.py afterward to add Stellar Age: Discovery.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


SOURCE_PAGES = {
    0: "Observatory",
    2: "StatueofZeus",
    3: "Colosseum",
    4: "CathedralofAachen",
    5: "StMarksBasilica",
    6: "CasteldelMonte",
    7: "DealCastle",
    8: "RoyalAlbertHall",
    9: "Alcatraz",
    10: "Atomium",
    11: "CapeCanaveral",
    12: "InnovationTower",
    13: "TruceTower",
    14: "RainForestProject",
    15: "ArcticOrangery",
    16: "TheBlueGalaxy",
    17: "HimejiCastle",
    18: "TheVirgoProject",
    19: "SpaceCarrier",
    20: "FlyingIsland",
    21: "A.I.Core",
    22: "SaturnVIGateCENTAURUS",
    23: "CosmicCatalyst",
}

BASE_URL = "https://foe.kwister.net/GB_list/{slug}"

# The source site suppresses a rank's blueprint cell when that rank has no FP
# payout.  The game still returns these P5 blueprint rewards.  Levels 5-16 are
# verified by captured GreatBuildingsService.getConstruction responses; level
# 4 is documented by the game's community wiki table.
BLUEPRINT_P5_OVERRIDES = {
    4: 1,
    **{level: 1 for level in range(5, 14)},
    **{level: 2 for level in range(14, 17)},
}


def fetch_pages(slug: str) -> list[str]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        (
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/140 Safari/537.36",
        )
    ]
    url = BASE_URL.format(slug=slug)
    opener.open(url, timeout=30).read()
    post = urllib.parse.urlencode({"arc_level": "1", "arc_toggle": "0"}).encode()
    opener.open(urllib.request.Request(url, data=post), timeout=30).read()
    return [
        opener.open(f"{url}?page={page}", timeout=30).read().decode("utf-8")
        for page in range(3)
    ]


def parse_value(row: str, label: str) -> int:
    match = re.search(rf"(?:\*)?{label}:\s*(?:\*)?([\d,]+|-)", row)
    if not match:
        return 0
    return 0 if match.group(1) == "-" else int(match.group(1).replace(",", ""))


def parse_pages(pages: list[str]) -> dict[int, dict[str, list[int]]]:
    parsed: dict[int, dict[str, list[int]]] = {}
    for page in pages:
        starts = list(re.finditer(r"<tr id=['\"](\d+)['\"]>", page))
        for index, start in enumerate(starts):
            level = int(start.group(1))
            end = starts[index + 1].start() if index + 1 < len(starts) else len(page)
            segment = page[start.start() : end]
            block_match = re.search(
                r"START GB REWARD TABLE -->(.*?)<!-- END GB REWARD TABLE",
                segment,
                re.DOTALL,
            )
            if not block_match:
                continue
            rank_rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", block_match.group(1), re.DOTALL)
            if len(rank_rows) != 5:
                raise ValueError(f"Expected five ranks at level {level}, got {len(rank_rows)}")
            parsed[level] = {
                "fp": [parse_value(row, "FP") for row in rank_rows],
                "medals": [parse_value(row, "Medals") for row in rank_rows],
                "blueprints": [parse_value(row, "Blueprints") for row in rank_rows],
            }

    if not parsed:
        raise ValueError("Source page did not contain any target levels")
    return parsed


def build_tables() -> dict[str, object]:
    medal_p1_by_era: dict[str, list[int]] = {}
    blueprint_candidates: list[list[list[int] | None]] = []
    fp_p1_by_era: dict[str, list[int]] = {}

    def fetch_one(item: tuple[int, str]) -> tuple[int, str, dict[int, dict[str, list[int]]]]:
        era_id, slug = item
        print(f"Fetching era {era_id}: {slug}", flush=True)
        error: Exception | None = None
        for attempt in range(4):
            try:
                return era_id, slug, parse_pages(fetch_pages(slug))
            except Exception as caught:  # Network source occasionally throttles.
                error = caught
                time.sleep(attempt + 1)
        print(f"Warning: no usable table for era {era_id} ({slug}): {error}", flush=True)
        return era_id, slug, {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fetched = list(executor.map(fetch_one, SOURCE_PAGES.items()))

    for era_id, slug, rows in sorted(fetched):
        missing = sorted(set(range(1, 202)) - rows.keys())
        if missing:
            raise ValueError(f"Era {era_id} source {slug} is missing target levels: {missing}")
        medals = [rows[level]["medals"] if level in rows else None for level in range(1, 202)]
        blueprints = [
            rows[level]["blueprints"] if level in rows else None for level in range(1, 202)
        ]
        fp = [rows[level]["fp"][0] if level in rows else None for level in range(1, 202)]
        medal_p1_by_era[str(era_id)] = [values[0] for values in medals]
        blueprint_candidates.append(blueprints)
        fp_p1_by_era[str(era_id)] = fp

    blueprints_by_level = [
        [
            max((table[level][rank] for table in blueprint_candidates if table[level]), default=0)
            for rank in range(5)
        ]
        for level in range(201)
    ]
    for level, value in BLUEPRINT_P5_OVERRIDES.items():
        blueprints_by_level[level - 1][4] = value

    return {
        "schemaVersion": 1,
        "throughTargetLevel": 201,
        "source": "https://foe.kwister.net/GB_list/",
        "sourcePagesByEra": {str(key): value for key, value in SOURCE_PAGES.items()},
        "medalMaxTargetLevelByEra": {
            era: len(values) for era, values in medal_p1_by_era.items()
        },
        "medalP1ByEra": medal_p1_by_era,
        "blueprintsByLevel": blueprints_by_level,
        "normalization": {
            "medalPositions": "P1, round(P1/2), round(P1/4), round(P1/10), round(P1/20)",
            "blueprintP5Overrides": BLUEPRINT_P5_OVERRIDES,
        },
        "validationFpP1ByEra": fp_p1_by_era,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/contributor-rewards-source.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = build_tables()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote contributor rewards to {args.output}")


if __name__ == "__main__":
    main()
