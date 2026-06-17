#!/usr/bin/env python3
"""Report main-city buildings for guild raids AP collection and attacker boosts."""
from __future__ import annotations

import argparse
import json
import math
import os
from glob import glob
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TARGET_BOOST_TYPE = "guild_raids_action_points_collection"
ATTACKER_BOOST_TYPES = {
    "att_boost_attacker",
    "def_boost_attacker",
    "att_def_boost_attacker",
}
GUILD_RAIDS_TARGETED_FEATURES = {"guild_raids"}


def latest_city_file() -> str:
    files = glob(os.path.join(INPUT_DIR, "city_*.json"))
    if not files:
        raise SystemExit(f"No city JSON files found in {INPUT_DIR}")
    return max(files, key=os.path.getmtime)


def load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    if isinstance(raw, dict):
        return raw
    raise SystemExit("Unexpected JSON payload format")


def iter_map_items(city_map: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(city_map, dict):
        for key, value in city_map.items():
            if isinstance(value, dict):
                yield str(key), value
        return
    if isinstance(city_map, list):
        for idx, value in enumerate(city_map):
            if isinstance(value, dict):
                yield str(idx), value


def detect_current_era(city_map: Any) -> Optional[str]:
    for _key, entry in iter_map_items(city_map):
        if entry.get("type") != "main_building":
            continue
        cityentity_id = entry.get("cityentity_id")
        if not isinstance(cityentity_id, str):
            continue
        parts = cityentity_id.split("_")
        if len(parts) >= 3 and parts[-1] == "Townhall":
            return parts[1]
    return None


def as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_boosts(component: Dict[str, Any], boost_types: Set[str]) -> List[Dict[str, Any]]:
    boost_component = component.get("boosts")
    if not isinstance(boost_component, dict):
        return []
    boosts = boost_component.get("boosts")
    if not isinstance(boosts, list):
        return []

    out: List[Dict[str, Any]] = []
    for boost in boosts:
        if not isinstance(boost, dict):
            continue
        boost_type = boost.get("type")
        if boost_type not in boost_types:
            continue
        value = as_float(boost.get("value"))
        if value is None:
            continue
        targeted_feature = boost.get("targetedFeature")
        out.append(
            {
                "boost_type": boost_type,
                "value": value,
                "targeted_feature": targeted_feature if isinstance(targeted_feature, str) else "",
            }
        )
    return out


def parse_ap_collection_boosts(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    return parse_boosts(component, {TARGET_BOOST_TYPE})


def parse_attacker_boosts(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = parse_boosts(component, ATTACKER_BOOST_TYPES)
    return [record for record in records if record["targeted_feature"] in GUILD_RAIDS_TARGETED_FEATURES]


def collect_records_from_entity(
    entity: Dict[str, Any],
    era: str,
    parser: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], str]:
    components = entity.get("components")
    if not isinstance(components, dict):
        return [], ""
    era_component = components.get(era)
    if isinstance(era_component, dict):
        era_records = parser(era_component)
        if era_records:
            return era_records, era
    all_age_component = components.get("AllAge")
    if isinstance(all_age_component, dict):
        all_age_records = parser(all_age_component)
        if all_age_records:
            return all_age_records, "AllAge"
    return [], ""


def extract_allowed_grid_ids(entity: Dict[str, Any], era: str) -> List[str]:
    components = entity.get("components")
    if not isinstance(components, dict):
        return []

    candidate_components: List[Dict[str, Any]] = []
    all_age = components.get("AllAge")
    if isinstance(all_age, dict):
        candidate_components.append(all_age)
    era_component = components.get(era)
    if isinstance(era_component, dict):
        candidate_components.append(era_component)

    for component in candidate_components:
        placement = component.get("placement")
        if not isinstance(placement, dict):
            continue
        allowed = placement.get("allowedPlacements")
        if not isinstance(allowed, list):
            continue
        grid_ids: List[str] = []
        for item in allowed:
            if not isinstance(item, dict):
                continue
            grid_id = item.get("gridId")
            if isinstance(grid_id, str):
                grid_ids.append(grid_id)
        if grid_ids:
            return grid_ids
    return []


def is_placeable_in_main_city(entity: Dict[str, Any], era: str) -> bool:
    grid_ids = extract_allowed_grid_ids(entity, era)
    if not grid_ids:
        return True
    return "main" in grid_ids


def extract_size(entity: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    components = entity.get("components")
    if isinstance(components, dict):
        all_age = components.get("AllAge")
        if isinstance(all_age, dict):
            placement = all_age.get("placement")
            if isinstance(placement, dict):
                size = placement.get("size")
                if isinstance(size, dict):
                    x = size.get("x")
                    y = size.get("y")
                    if isinstance(x, int) and isinstance(y, int):
                        return x, y
    width = entity.get("width")
    length = entity.get("length")
    if isinstance(width, int) and isinstance(length, int):
        return width, length
    return None


def format_number(value: float) -> str:
    if math.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:.2f}"


def aggregate_buildings(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for entry in entries:
        size = entry.get("size")
        area = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"
        total_boost = sum(float(record["value"]) for record in entry.get("records", []))
        per_tile = total_boost / area if area else 0.0
        ranked.append(
            {
                "name": entry["name"],
                "size_label": size_label,
                "area": area,
                "total_boost": total_boost,
                "per_tile": per_tile,
                "records": entry["records"],
                "component_source": entry.get("component_source", ""),
            }
        )
    ranked.sort(key=lambda item: (-item["total_boost"], -item["per_tile"], item["name"]))
    return ranked


def aggregate_attacker_boost_buildings(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for entry in entries:
        size = entry.get("size")
        area = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"

        attack_boost = 0.0
        defense_boost = 0.0
        for record in entry.get("records", []):
            value = float(record["value"])
            boost_type = record.get("boost_type")
            if boost_type == "att_boost_attacker":
                attack_boost += value
            elif boost_type == "def_boost_attacker":
                defense_boost += value
            elif boost_type == "att_def_boost_attacker":
                attack_boost += value
                defense_boost += value

        total_attacker_boost = attack_boost + defense_boost
        ranked.append(
            {
                "name": entry["name"],
                "size_label": size_label,
                "area": area,
                "attack_boost": attack_boost,
                "defense_boost": defense_boost,
                "total_attacker_boost": total_attacker_boost,
                "records": entry["records"],
                "component_source": entry.get("component_source", ""),
            }
        )
    ranked.sort(key=lambda item: (-item["total_attacker_boost"], item["name"]))
    return ranked


def write_ap_report(path: str, source_file: str, era: str, buildings: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append(f"Source file: {source_file}")
    lines.append(f"Era: {era}")
    lines.append(f"Boost type: {TARGET_BOOST_TYPE}")
    lines.append(f"Total buildings: {len(buildings)}")
    lines.append("")
    for idx, info in enumerate(buildings, start=1):
        lines.append(
            f"{idx}. {info['name']} | size {info['size_label']} | AP collection boost {format_number(info['total_boost'])}"
        )
        if info.get("area"):
            lines.append(f"   AP collection boost per tile: {info['per_tile']:.3f}")
        else:
            lines.append("   AP collection boost per tile: n/a")
        component_source = info.get("component_source")
        if component_source:
            lines.append(f"   Component source: {component_source}")
        for record in info.get("records", []):
            target = record.get("targeted_feature") or "n/a"
            lines.append(
                f"   - boost value {format_number(record['value'])} | targetedFeature={target}"
            )
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def write_attacker_report(path: str, source_file: str, era: str, buildings: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append(f"Source file: {source_file}")
    lines.append(f"Era: {era}")
    lines.append("Boost types: att_boost_attacker, def_boost_attacker, att_def_boost_attacker")
    lines.append("targetedFeature included: guild_raids")
    lines.append(f"Total buildings: {len(buildings)}")
    lines.append("")
    for idx, info in enumerate(buildings, start=1):
        lines.append(
            f"{idx}. {info['name']} | size {info['size_label']} | attack+defense sum {format_number(info['total_attacker_boost'])} | attack boost {format_number(info['attack_boost'])} | defense boost {format_number(info['defense_boost'])}"
        )
        if info.get("area"):
            area = float(info["area"])
            lines.append(
                f"   Per tile: attack {info['attack_boost'] / area:.3f} | defense {info['defense_boost'] / area:.3f}"
            )
        else:
            lines.append("   Per tile: attack n/a | defense n/a")
        component_source = info.get("component_source")
        if component_source:
            lines.append(f"   Component source: {component_source}")
        for record in info.get("records", []):
            target = record.get("targeted_feature") or "n/a"
            boost_type = record.get("boost_type") or "n/a"
            lines.append(
                f"   - type {boost_type} | value {format_number(record['value'])} | targetedFeature={target}"
            )
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report buildings with guild_raids_action_points_collection boost"
    )
    parser.add_argument(
        "--era",
        default=None,
        help="Era component to inspect (e.g. VirtualFuture). Default: auto-detect from town hall.",
    )
    args = parser.parse_args()

    if not os.path.isdir(INPUT_DIR):
        raise SystemExit(f"Input directory not found: {INPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    latest_file = latest_city_file()
    payload = load_payload(latest_file)

    entities = payload.get("CityEntities")
    if not isinstance(entities, dict):
        raise SystemExit("CityEntities not found in JSON")

    chosen_era = args.era
    if not chosen_era:
        chosen_era = detect_current_era(payload.get("CityMapData"))
    if not chosen_era:
        raise SystemExit(
            "Could not auto-detect era from CityMapData. Re-run with --era <EraName> (example: --era VirtualFuture)."
        )

    ap_matches: List[Dict[str, Any]] = []
    attacker_matches: List[Dict[str, Any]] = []
    excluded_non_main_ap = 0
    excluded_non_main_attacker = 0
    for entity in entities.values():
        if not isinstance(entity, dict):
            continue

        ap_records, ap_component_source = collect_records_from_entity(
            entity, chosen_era, parse_ap_collection_boosts
        )
        attacker_records, attacker_component_source = collect_records_from_entity(
            entity, chosen_era, parse_attacker_boosts
        )
        if not ap_records and not attacker_records:
            continue

        placeable_in_main = is_placeable_in_main_city(entity, chosen_era)
        if ap_records and not placeable_in_main:
            excluded_non_main_ap += 1
        if attacker_records and not placeable_in_main:
            excluded_non_main_attacker += 1
        if not placeable_in_main:
            continue

        if ap_records:
            ap_matches.append(
                {
                    "id": entity.get("id"),
                    "name": entity.get("name", entity.get("id")),
                    "size": extract_size(entity),
                    "records": ap_records,
                    "component_source": ap_component_source,
                }
            )
        if attacker_records:
            attacker_matches.append(
                {
                    "id": entity.get("id"),
                    "name": entity.get("name", entity.get("id")),
                    "size": extract_size(entity),
                    "records": attacker_records,
                    "component_source": attacker_component_source,
                }
            )

    ranked_ap = aggregate_buildings(ap_matches)
    ranked_attacker = aggregate_attacker_boost_buildings(attacker_matches)
    safe_era = chosen_era.replace(" ", "_")
    ap_report_path = os.path.join(OUTPUT_DIR, f"guild_raids_action_points_collection_{safe_era}.txt")
    attacker_report_path = os.path.join(OUTPUT_DIR, f"guild_raids_attacker_boosts_{safe_era}.txt")
    write_ap_report(ap_report_path, latest_file, chosen_era, ranked_ap)
    write_attacker_report(attacker_report_path, latest_file, chosen_era, ranked_attacker)

    print(f"Latest file: {latest_file}")
    print(f"Era inspected: {chosen_era}")
    print(f"AP buildings found: {len(ranked_ap)}")
    print(f"AP excluded non-main-city buildings: {excluded_non_main_ap}")
    print(f"AP report: {ap_report_path}")
    print(f"Attacker boost buildings found: {len(ranked_attacker)}")
    print(f"Attacker boost excluded non-main-city buildings: {excluded_non_main_attacker}")
    print(f"Attacker boost report: {attacker_report_path}")


if __name__ == "__main__":
    main()
