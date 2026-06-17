#!/usr/bin/env python3
"""Rank buildings that produce Great Building blueprints in a given era."""
from __future__ import annotations

import argparse
import json
import math
import os
from glob import glob
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE_DIR = os.path.expanduser("~/Documents/FOE/CityAnalysis")
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DROP_KEYS = ("dropChance", "drop_chance", "chance", "probability")


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
        # Expected shape: H_VirtualFuture_Townhall
        parts = cityentity_id.split("_")
        if len(parts) >= 3 and parts[-1] == "Townhall":
            return parts[1]
    return None


def reward_lookup(component: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup = component.get("lookup")
    if not isinstance(lookup, dict):
        return {}
    rewards = lookup.get("rewards")
    if isinstance(rewards, dict):
        return rewards
    if isinstance(rewards, list):
        out: Dict[str, Dict[str, Any]] = {}
        for entry in rewards:
            if not isinstance(entry, dict):
                continue
            rid = entry.get("id")
            if isinstance(rid, str):
                out[rid] = entry
        return out
    return {}


def normalize_probability(value: Any) -> Optional[float]:
    numeric = _as_float(value)
    if numeric is None:
        return None
    if numeric > 1:
        return numeric / 100.0
    return numeric


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def iter_reward_products(
    component: Dict[str, Any]
) -> Iterable[Tuple[Optional[str], Dict[str, Any], Optional[str], Optional[int], Optional[float], bool]]:
    production = component.get("production")
    if not isinstance(production, dict):
        return
    options = production.get("options")
    if not isinstance(options, list):
        return

    def walk_product(
        product: Dict[str, Any],
        option_name: Optional[str],
        option_time: Optional[int],
        drop_chance: Optional[float],
        requires_motivation: bool,
    ):
        if not isinstance(product, dict):
            return

        ptype = product.get("type")
        reward_dict = product.get("reward") if isinstance(product.get("reward"), dict) else None

        if ptype == "genericReward" and reward_dict:
            rid = reward_dict.get("id") if isinstance(reward_dict.get("id"), str) else None
            yield rid, reward_dict, option_name, option_time, drop_chance, requires_motivation
            return

        if ptype == "random":
            sub_products = product.get("products", [])
            if isinstance(sub_products, list):
                for sub in sub_products:
                    if not isinstance(sub, dict):
                        continue
                    nested = sub.get("product") or sub.get("reward")
                    nested_drop = None
                    for key in DROP_KEYS:
                        if key in sub:
                            nested_drop = normalize_probability(sub.get(key))
                            break
                    nested_requires = requires_motivation or bool(sub.get("onlyWhenMotivated"))
                    if isinstance(nested, dict):
                        yield from walk_product(
                            nested,
                            option_name,
                            option_time,
                            nested_drop if nested_drop is not None else drop_chance,
                            nested_requires,
                        )
            return

        if ptype == "chest":
            possibles = product.get("possible_rewards") or product.get("possibleRewards")
            if isinstance(possibles, list):
                for candidate in possibles:
                    if not isinstance(candidate, dict):
                        continue
                    reward = candidate.get("reward")
                    if not isinstance(reward, dict):
                        continue
                    cand_drop = None
                    for key in DROP_KEYS:
                        if key in candidate:
                            cand_drop = normalize_probability(candidate.get(key))
                            break
                    rid = reward.get("id") if isinstance(reward.get("id"), str) else None
                    yield rid, reward, option_name, option_time, cand_drop, requires_motivation
            return

        if reward_dict:
            rid = reward_dict.get("id") if isinstance(reward_dict.get("id"), str) else None
            yield rid, reward_dict, option_name, option_time, drop_chance, requires_motivation

    for option in options:
        if not isinstance(option, dict):
            continue
        option_name = option.get("name")
        option_time = option.get("time")
        option_requires = bool(option.get("onlyWhenMotivated"))
        products = option.get("products", [])
        if not isinstance(products, list):
            continue
        for product in products:
            if not isinstance(product, dict):
                continue
            product_requires = option_requires or bool(product.get("onlyWhenMotivated"))
            prod_drop = None
            for key in DROP_KEYS:
                if key in product:
                    prod_drop = normalize_probability(product.get(key))
                    break
            yield from walk_product(product, option_name, option_time, prod_drop, product_requires)


def parse_blueprint_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    if entry.get("type") != "blueprint":
        return None
    amount = _as_float(entry.get("amount"))
    if amount is None or amount <= 0:
        return None
    tier_value = ""
    tier = entry.get("tier")
    if isinstance(tier, dict) and isinstance(tier.get("value"), str):
        tier_value = tier["value"]
    return {
        "amount": amount,
        "name": entry.get("name", "Blueprint"),
        "tier": tier_value,
    }


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


def extract_street_requirement(entity: Dict[str, Any], component: Dict[str, Any]) -> Optional[int]:
    def parse(req_obj: Any) -> Optional[int]:
        if isinstance(req_obj, dict):
            if isinstance(req_obj.get("requiredLevel"), int):
                return req_obj["requiredLevel"]
            if isinstance(req_obj.get("street_connection_level"), int):
                return req_obj["street_connection_level"]
        if isinstance(req_obj, int):
            return req_obj
        return None

    components = entity.get("components")
    if isinstance(components, dict):
        all_age = components.get("AllAge")
        if isinstance(all_age, dict):
            req = parse(all_age.get("streetConnectionRequirement"))
            if req is not None:
                return req
    req = parse(component.get("streetConnectionRequirement"))
    if req is not None:
        return req
    requirements = entity.get("requirements")
    if isinstance(requirements, dict):
        req = parse(requirements.get("street_connection_level"))
        if req is not None:
            return req
    return None


def format_time_label(time_seconds: Optional[int]) -> str:
    if not isinstance(time_seconds, int):
        return ""
    if time_seconds % 3600 == 0:
        return f"{time_seconds // 3600}h"
    return f"{time_seconds}s"


def format_number(value: float) -> str:
    if math.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:.2f}"


def format_probability(prob: Optional[float]) -> str:
    if prob is None:
        return ""
    pct = prob * 100
    if math.isclose(pct, round(pct)):
        return f"{int(round(pct))}%"
    return f"{pct:.1f}%"


def aggregate_blueprint_buildings(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for entry in matches:
        size = entry.get("size")
        area = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"
        expected = 0.0
        for record in entry.get("records", []):
            probability = record.get("probability")
            effective_prob = probability if isinstance(probability, (int, float)) else 1.0
            expected += float(record["amount"]) * float(effective_prob)
        efficiency = expected / area if area else 0.0
        ranked.append(
            {
                "name": entry["name"],
                "size_label": size_label,
                "street": entry.get("street"),
                "records": entry["records"],
                "expected": expected,
                "efficiency": efficiency,
                "area": area,
            }
        )
    ranked.sort(key=lambda item: (-item["efficiency"], -item["expected"], item["name"]))
    return ranked


def write_report(path: str, source_file: str, era: str, buildings: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append(f"Source file: {source_file}")
    lines.append(f"Era: {era}")
    lines.append(f"Total buildings: {len(buildings)}")
    lines.append("")
    for idx, info in enumerate(buildings, start=1):
        street = info.get("street")
        street_label = str(street) if street is not None else "n/a"
        efficiency = info.get("efficiency", 0.0)
        efficiency_label = f"{efficiency:.3f}" if info.get("area") else "n/a"
        expected = info.get("expected", 0.0)
        lines.append(
            f"{idx}. {info['name']} | size {info['size_label']} | street {street_label} | efficiency {efficiency_label} blueprints/tile"
        )
        lines.append(f"   Expected blueprints per cycle: {format_number(expected)}")
        for record in info.get("records", []):
            tier = record.get("tier")
            tier_suffix = f" [{tier}]" if tier else ""
            chance_label = format_probability(record.get("probability"))
            chance_suffix = f" @ {chance_label} chance" if chance_label else ""
            motivation_suffix = " (needs motivation)" if record.get("needs_motivation") else ""
            time_label = record.get("time_label")
            time_suffix = f" ({time_label})" if time_label else ""
            lines.append(
                f"   - {format_number(record['amount'])} blueprint{'' if math.isclose(record['amount'], 1.0) else 's'}{tier_suffix}{time_suffix}{chance_suffix}{motivation_suffix}"
            )
        lines.append("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank buildings that produce Great Building blueprints")
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
    for entity in entities.values():
        if not isinstance(entity, dict):
            continue
        components = entity.get("components")
        if not isinstance(components, dict):
            continue
        era_component = components.get(chosen_era)
        if not isinstance(era_component, dict):
            continue

        lookup = reward_lookup(era_component)
        records: List[Dict[str, Any]] = []
        for reward_id, fallback, _option_name, option_time, drop_chance, requires_motivation in iter_reward_products(
            era_component
        ):
            reward_entry = lookup.get(reward_id, fallback)
            parsed = parse_blueprint_entry(reward_entry)
            if not parsed:
                continue
            records.append(
                {
                    "amount": parsed["amount"],
                    "tier": parsed["tier"],
                    "time_label": format_time_label(option_time),
                    "probability": drop_chance if isinstance(drop_chance, (int, float)) else None,
                    "needs_motivation": requires_motivation,
                }
            )

        if not records:
            continue

        matches.append(
            {
                "id": entity.get("id"),
                "name": entity.get("name", entity.get("id")),
                "size": extract_size(entity),
                "street": extract_street_requirement(entity, era_component),
                "records": records,
            }
        )

    ranked = aggregate_blueprint_buildings(matches)
    safe_era = chosen_era.replace(" ", "_")
    report_path = os.path.join(OUTPUT_DIR, f"blueprint_buildings_{safe_era}.txt")
    write_report(report_path, latest_file, chosen_era, ranked)

    print(f"Latest file: {latest_file}")
    print(f"Era inspected: {chosen_era}")
    print(f"Total buildings ranked: {len(ranked)}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
