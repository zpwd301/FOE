#!/usr/bin/env python3
"""Report main-city buildings that provide forge point percentage boosts."""
from __future__ import annotations

import argparse
import json
import math
import os
from glob import glob
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TARGET_BOOST_TYPE = "forge_points_production"


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


def parse_fp_boosts(component: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        if boost.get("type") != TARGET_BOOST_TYPE:
            continue
        value = as_float(boost.get("value"))
        if value is None:
            continue
        targeted_feature = boost.get("targetedFeature")
        out.append(
            {
                "value": value,
                "targeted_feature": targeted_feature if isinstance(targeted_feature, str) else "",
            }
        )
    return out


def collect_records_from_entity(entity: Dict[str, Any], era: str) -> Tuple[List[Dict[str, Any]], str]:
    components = entity.get("components")
    if not isinstance(components, dict):
        return [], ""
    era_component = components.get(era)
    if isinstance(era_component, dict):
        era_records = parse_fp_boosts(era_component)
        if era_records:
            return era_records, era
    all_age_component = components.get("AllAge")
    if isinstance(all_age_component, dict):
        all_age_records = parse_fp_boosts(all_age_component)
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


def extract_size(entity: Dict[str, Any], era: str) -> Optional[Tuple[int, int]]:
    components = entity.get("components")
    if isinstance(components, dict):
        for key in (era, "AllAge"):
            component = components.get(key)
            if not isinstance(component, dict):
                continue
            placement = component.get("placement")
            if not isinstance(placement, dict):
                continue
            size = placement.get("size")
            if not isinstance(size, dict):
                continue
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
        area: Optional[int] = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"

        total_boost = sum(float(record["value"]) for record in entry.get("records", []))
        per_tile = total_boost / area if area else 0.0
        ranked.append(
            {
                "name": entry["name"],
                "id": entry["id"],
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


def write_report(path: str, source_file: str, era: str, buildings: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append(f"Source file: {source_file}")
    lines.append(f"Era: {era}")
    lines.append(f"Boost type: {TARGET_BOOST_TYPE}")
    lines.append("Value unit: FP production %")
    lines.append(f"Total buildings: {len(buildings)}")
    lines.append("")

    for idx, info in enumerate(buildings, start=1):
        lines.append(
            f"{idx}. {info['name']} | size {info['size_label']} | FP boost {format_number(info['total_boost'])}%"
        )
        if info.get("area"):
            lines.append(f"   FP boost per tile: {info['per_tile']:.3f}%")
        else:
            lines.append("   FP boost per tile: n/a")
        lines.append(f"   CityEntity ID: {info['id']}")

        component_source = info.get("component_source")
        if component_source:
            lines.append(f"   Component source: {component_source}")

        for record in info.get("records", []):
            target = record.get("targeted_feature") or "n/a"
            lines.append(f"   - boost value {format_number(record['value'])}% | targetedFeature={target}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report buildings with forge_points_production boost"
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

    matches: List[Dict[str, Any]] = []
    excluded_non_main = 0
    for entity in entities.values():
        if not isinstance(entity, dict):
            continue

        records, component_source = collect_records_from_entity(entity, chosen_era)
        if not records:
            continue

        if not is_placeable_in_main_city(entity, chosen_era):
            excluded_non_main += 1
            continue

        matches.append(
            {
                "id": entity.get("id", ""),
                "name": entity.get("name", entity.get("id", "")),
                "size": extract_size(entity, chosen_era),
                "records": records,
                "component_source": component_source,
            }
        )

    ranked = aggregate_buildings(matches)
    safe_era = chosen_era.replace(" ", "_")
    report_path = os.path.join(OUTPUT_DIR, f"forge_points_boost_buildings_{safe_era}.txt")
    write_report(report_path, latest_file, chosen_era, ranked)

    print(f"Latest file: {latest_file}")
    print(f"Era inspected: {chosen_era}")
    print(f"FP boost buildings found: {len(ranked)}")
    print(f"FP boost excluded non-main-city buildings: {excluded_non_main}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
