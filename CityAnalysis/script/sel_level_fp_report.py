#!/usr/bin/env python3
"""Generate age-aware FP reports from a map export using input/ref/zpwd-ref as reference."""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Counter as CounterType, DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple

AGE_BY_LEVEL: Dict[int, Tuple[str, str]] = {
    0: ("SA", "StoneAge"),
    1: ("BA", "BronzeAge"),
    2: ("IA", "IronAge"),
    3: ("EMA", "EarlyMiddleAge"),
    4: ("HMA", "HighMiddleAge"),
    5: ("LMA", "LateMiddleAge"),
    6: ("CA", "ColonialAge"),
    7: ("INA", "IndustrialAge"),
    8: ("PE", "ProgressiveEra"),
    9: ("ME", "ModernEra"),
    10: ("PME", "PostModernEra"),
    11: ("CE", "ContemporaryEra"),
    12: ("TE", "TomorrowEra"),
    13: ("FE", "FutureEra"),
    14: ("AF", "ArcticFuture"),
    15: ("OF", "OceanicFuture"),
    16: ("VF", "VirtualFuture"),
    17: ("SAM", "SpaceAgeMars"),
    18: ("SAAB", "SpaceAgeAsteroidBelt"),
    19: ("SAV", "SpaceAgeVenus"),
    20: ("SAJM", "SpaceAgeJupiterMoon"),
    21: ("SAT", "SpaceAgeTitan"),
    22: ("SASH", "SpaceAgeSpaceHub"),
}

FIELDNAMES_AVERAGE_FP = [
    "AverageExpectedFP",
    "BaseFP",
    "Name",
    "Level",
    "Age",
    "Count",
    "PassiveFPBoost",
    "Production",
]

REWARDED_UNIT_TYPE_LABELS = {
    "light_melee": "light melee",
    "short_ranged": "short ranged",
    "fast": "fast",
    "heavy_melee": "heavy melee",
    "long_ranged": "long ranged",
}

RESOURCE_LABELS = {
    "strategy_points": "FP",
    "money": "coins",
    "supplies": "supplies",
    "medals": "medals",
    "population": "population",
    "random_good_of_age": "random good of age",
    "random_good_of_previous_age": "random good of previous age",
    "random_good_of_next_age": "random good of next age",
    "all_goods_of_age": "all goods of age",
    "all_goods_of_previous_age": "all goods of previous age",
    "all_goods_of_next_age": "all goods of next age",
    "random_special_good_up_to_age": "random special good up to age",
    "clan_power": "guild power",
}


@dataclass(frozen=True)
class EntityKey:
    cityentity_id: str
    level: int
    entity_type: str


@dataclass
class ReportRow:
    key: EntityKey
    name: str
    age_code: str
    count: int
    passive_fp_boost: Decimal
    production: str


def default_map_path(input_dir: Path) -> Path:
    for candidate in ("sel", "zpwd-sel"):
        path = input_dir / candidate
        if path.exists():
            return path

    city_files = sorted(input_dir.glob("city_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if city_files:
        return city_files[0]
    return input_dir / "sel"


def parse_args() -> argparse.Namespace:
    base_dir = Path(__file__).resolve().parents[1]
    output_dir = base_dir / "output"

    parser = argparse.ArgumentParser(
        description="Generate leveled-building FP reports from a map export and input/ref/zpwd-ref."
    )
    parser.add_argument(
        "--input",
        "--map-file",
        "--sel",
        dest="map_file",
        type=Path,
        default=None,
        help="Path to the map JSON file. Explicit input writes TSV only.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=output_dir,
        help="Directory for generated TSV reports.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def output_basename(map_file: Path) -> str:
    return map_file.name if map_file.suffix == "" else map_file.stem


def convert_tsv_to_excel(tsv_path: Path) -> Path:
    base_dir = Path(__file__).resolve().parents[1]
    converter_path = base_dir / "script" / "average_fp_tsv_to_excel.py"
    venv_python = base_dir / ".venv" / "bin" / "python"
    python_executable = venv_python if venv_python.exists() else Path(sys.executable)
    xlsx_path = tsv_path.with_suffix(".xlsx")
    subprocess.run(
        [str(python_executable), str(converter_path), "--input", str(tsv_path), "--output", str(xlsx_path)],
        check=True,
    )
    return xlsx_path


def walk_objects(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_objects(item)


def build_entity_index(reference_data: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    entity_defs: Dict[str, Dict[str, Any]] = {}
    name_by_id: Dict[str, str] = {}
    for obj in walk_objects(reference_data):
        entity_id = obj.get("id")
        if isinstance(entity_id, str):
            entity_defs[entity_id] = obj
            name = obj.get("name")
            if isinstance(name, str):
                name_by_id[entity_id] = name
    return entity_defs, name_by_id


def iter_map_entities(map_data: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(map_data, list):
        for item in map_data:
            if not isinstance(item, dict):
                continue
            response_data = item.get("responseData")
            if not isinstance(response_data, dict):
                continue
            city_map = response_data.get("city_map")
            if not isinstance(city_map, dict):
                continue
            entities = city_map.get("entities")
            if not isinstance(entities, list):
                continue
            for entity in entities:
                if isinstance(entity, dict):
                    yield entity
        return

    if isinstance(map_data, dict):
        if isinstance(map_data.get("data"), dict):
            yield from iter_map_entities(map_data["data"])
            return
        city_map_data = map_data.get("CityMapData")
        if isinstance(city_map_data, dict):
            for entity in city_map_data.values():
                if isinstance(entity, dict):
                    yield entity
        elif isinstance(map_data.get("entities"), list):
            for entity in map_data["entities"]:
                if isinstance(entity, dict):
                    yield entity


def collect_map_entries(map_data: Any) -> CounterType[EntityKey]:
    counts: CounterType[EntityKey] = Counter()
    for entity in iter_map_entities(map_data):
        level = entity.get("level")
        if not isinstance(level, int):
            continue
        entity_type = entity.get("type")
        cityentity_id = entity.get("cityentity_id")
        if entity_type == "greatbuilding" or not isinstance(cityentity_id, str):
            continue
        counts[EntityKey(cityentity_id, level, str(entity_type))] += 1
    return counts


def format_time(seconds: int) -> str:
    if seconds == 86400:
        return "24h"
    if seconds > 0 and seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds > 0 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds > 0 and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def human_resource_key(key: str) -> str:
    return RESOURCE_LABELS.get(key, key.replace("_", " "))


def summarize_resources(resources: Optional[Dict[str, Any]]) -> str:
    if not isinstance(resources, dict):
        return ""
    parts: List[str] = []
    for key, value in resources.items():
        parts.append(f"{value} {human_resource_key(key)}")
    return ", ".join(parts)


def parse_reward_id(reward_id: str, name_by_id: Dict[str, str]) -> str:
    unit_match = re.fullmatch(r"era_unit#([^#]+)#([^#]+)#(\d+)", reward_id)
    if unit_match:
        unit_type, era_ref, amount = unit_match.groups()
        label = REWARDED_UNIT_TYPE_LABELS.get(unit_type, unit_type)
        era_label = era_ref.lower().replace("era", " era")
        return f"{amount} {era_label} {label} units"

    plain_unit_match = re.fullmatch(r"unit#([^#]+)#(\d+)", reward_id)
    if plain_unit_match:
        unit_type, amount = plain_unit_match.groups()
        return f"{amount} {unit_type.replace('_', ' ')}"

    blueprint_match = re.fullmatch(r"blueprint#([^#]+)#([^#]+)#(\d+)", reward_id)
    if blueprint_match:
        tier, kind, amount = blueprint_match.groups()
        return f"{amount} {kind} {tier} blueprints"

    fragment_match = re.fullmatch(r"fragment#([^#]+)#(\d+)", reward_id)
    if fragment_match:
        base_reward_id, amount = fragment_match.groups()
        base_name = name_by_id.get(base_reward_id, base_reward_id.replace("_", " "))
        return f"{amount} Fragments of {base_name}"

    return name_by_id.get(reward_id, reward_id.replace("_", " "))


def resolve_reward_name(
    reward: Dict[str, Any],
    lookup: Dict[str, Dict[str, Any]],
    name_by_id: Dict[str, str],
) -> str:
    reward_name = reward.get("name")
    if isinstance(reward_name, str):
        return reward_name
    reward_id = reward.get("id")
    if isinstance(reward_id, str) and reward_id in lookup:
        resolved = lookup[reward_id]
        resolved_name = resolved.get("name")
        if isinstance(resolved_name, str):
            return resolved_name
        return parse_reward_id(reward_id, name_by_id)
    if isinstance(reward_id, str):
        return parse_reward_id(reward_id, name_by_id)
    return json.dumps(reward, ensure_ascii=False)


def summarize_random_product(
    random_product: Dict[str, Any],
    lookup: Dict[str, Dict[str, Any]],
    name_by_id: Dict[str, str],
) -> str:
    parts: List[str] = []
    products = random_product.get("products")
    if not isinstance(products, list):
        return "random: []"
    for option in products:
        if not isinstance(option, dict):
            continue
        nested = option.get("product")
        if not isinstance(nested, dict):
            continue
        chance = option.get("dropChance")
        chance_label = ""
        if isinstance(chance, (int, float)):
            chance_label = f"{chance * 100:.1f}% "
        summary = summarize_product(nested, lookup, name_by_id, include_prefix=False)
        parts.append(f"{chance_label}{summary}".strip())
    return "random: " + " / ".join(parts)


def summarize_product(
    product: Dict[str, Any],
    lookup: Dict[str, Dict[str, Any]],
    name_by_id: Dict[str, str],
    *,
    include_prefix: bool,
) -> str:
    prefix = "motivated: " if include_prefix and product.get("onlyWhenMotivated") else ""
    product_type = product.get("type")

    if product_type == "resources":
        player_resources = product.get("playerResources", {}).get("resources")
        if player_resources is None:
            player_resources = product.get("product", {}).get("resources")
        return prefix + summarize_resources(player_resources)

    if product_type == "guildResources":
        guild_resources = product.get("guildResources", {}).get("resources")
        return prefix + summarize_resources(guild_resources)

    if product_type == "genericReward":
        reward = product.get("reward")
        if isinstance(reward, dict):
            return prefix + resolve_reward_name(reward, lookup, name_by_id)
        return prefix + str(reward)

    if product_type == "unit":
        amount = product.get("amount", "?")
        unit_type_id = str(product.get("unitTypeId", "unit")).replace("_", " ")
        return prefix + f"{amount} {unit_type_id}"

    if product_type == "random":
        random_summary = summarize_random_product(product, lookup, name_by_id)
        return prefix + random_summary if prefix else random_summary

    return prefix + json.dumps(product, ensure_ascii=False)


def summarize_production_component(
    entity_def: Dict[str, Any],
    era_name: str,
    name_by_id: Dict[str, str],
) -> Optional[str]:
    components = entity_def.get("components")
    if not isinstance(components, dict):
        return None

    lookup: Dict[str, Dict[str, Any]] = {}
    for component_name in ("AllAge", era_name):
        component = components.get(component_name)
        if not isinstance(component, dict):
            continue
        reward_lookup = component.get("lookup", {}).get("rewards")
        if isinstance(reward_lookup, dict):
            lookup.update(reward_lookup)

    production = components.get(era_name, {}).get("production")
    if not isinstance(production, dict):
        production = components.get("AllAge", {}).get("production")
    if not isinstance(production, dict):
        return None

    options = production.get("options")
    if not isinstance(options, list):
        return None

    option_parts: List[str] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        time_label = ""
        time_value = option.get("time")
        if isinstance(time_value, int):
            time_label = f"{format_time(time_value)}: "
        products = option.get("products")
        if not isinstance(products, list):
            continue
        summaries = [
            summarize_product(product, lookup, name_by_id, include_prefix=True)
            for product in products
            if isinstance(product, dict)
        ]
        summaries = [summary for summary in summaries if summary]
        option_parts.append(time_label + "; ".join(summaries))
    return " | ".join(option_parts) if option_parts else None


def summarize_entity_level_production(entity_def: Dict[str, Any], era_name: str) -> Optional[str]:
    levels = entity_def.get("entity_levels")
    available_products = entity_def.get("available_products")
    if not isinstance(levels, list) or not isinstance(available_products, list):
        return None

    era_entry = next((entry for entry in levels if entry.get("era") == era_name), None)
    if not isinstance(era_entry, dict):
        return None
    production_values = era_entry.get("production_values")
    if not isinstance(production_values, list):
        return None

    parts: List[str] = []
    for index, production_value in enumerate(production_values):
        if not isinstance(production_value, dict):
            continue
        label = ""
        if index < len(available_products) and isinstance(available_products[index], dict):
            product_name = available_products[index].get("name")
            product_time = available_products[index].get("production_time")
            fragments = []
            if isinstance(product_name, str):
                fragments.append(product_name)
            if isinstance(product_time, int):
                fragments.append(format_time(product_time))
            label = " ".join(fragments)
        body = f"{production_value.get('value', 0)} {human_resource_key(str(production_value.get('type', '')))}"
        parts.append(f"{label}: {body}" if label else body)
    return " | ".join(parts) if parts else None


def summarize_available_products(entity_def: Dict[str, Any]) -> Optional[str]:
    available_products = entity_def.get("available_products")
    if not isinstance(available_products, list):
        return None

    parts: List[str] = []
    for product in available_products:
        if not isinstance(product, dict):
            continue
        label_bits: List[str] = []
        name = product.get("name")
        if isinstance(name, str):
            label_bits.append(name)
        production_time = product.get("production_time")
        if isinstance(production_time, int):
            label_bits.append(format_time(production_time))
        label = " ".join(label_bits)

        body: Optional[str] = None
        resources = product.get("product", {}).get("resources")
        if isinstance(resources, dict) and resources:
            body = summarize_resources(resources)
        elif isinstance(product.get("amount"), int) and isinstance(product.get("unit_type_id"), str):
            body = f"{product['amount']} {product['unit_type_id'].replace('_', ' ')}"
        elif isinstance(product.get("amount"), int) and isinstance(name, str):
            body = f"{product['amount']} {name}"

        if body:
            parts.append(f"{label}: {body}" if label else body)
    return " | ".join(parts) if parts else None


def summarize_chain_piece(entity_def: Dict[str, Any]) -> Tuple[Decimal, Optional[str]]:
    chain = entity_def.get("components", {}).get("AllAge", {}).get("chain", {})
    bonuses = chain.get("config", {}).get("bonuses")
    if not isinstance(bonuses, list):
        return Decimal("0"), None

    total_fp = Decimal("0")
    texts: List[str] = []
    for bonus in bonuses:
        if not isinstance(bonus, dict):
            continue
        productions = bonus.get("productions")
        if not isinstance(productions, list):
            continue
        local_texts: List[str] = []
        for production in productions:
            if not isinstance(production, dict):
                continue
            text = summarize_product(production, {}, {}, include_prefix=False)
            if text:
                local_texts.append(text)
                for match in re.finditer(r"(\d+)\s+FP\b", text):
                    total_fp += Decimal(match.group(1))
        if local_texts:
            texts.append("; ".join(local_texts))
    return total_fp, " | ".join(texts) if texts else None


def summarize_passive_fp_boost(entity_def: Dict[str, Any], era_name: str) -> Tuple[Decimal, Optional[str]]:
    components = entity_def.get("components")
    if not isinstance(components, dict):
        return Decimal("0"), None

    boosts = components.get(era_name, {}).get("boosts", {}).get("boosts")
    if not isinstance(boosts, list):
        boosts = components.get("AllAge", {}).get("boosts", {}).get("boosts")
    if not isinstance(boosts, list):
        return Decimal("0"), None

    total = Decimal("0")
    parts: List[str] = []
    for boost in boosts:
        if not isinstance(boost, dict):
            continue
        if boost.get("type") != "forge_points_production":
            continue
        value = Decimal(str(boost.get("value", 0)))
        total += value
        parts.append(f"passive: +{value}% FP boost")
    return total, "; ".join(parts) if parts else None


def determine_chain_roles(
    keys: Sequence[EntityKey],
    entity_defs: Dict[str, Dict[str, Any]],
) -> Tuple[DefaultDict[str, List[EntityKey]], DefaultDict[str, List[EntityKey]]]:
    chain_mains: DefaultDict[str, List[EntityKey]] = defaultdict(list)
    chain_pieces: DefaultDict[str, List[EntityKey]] = defaultdict(list)

    for key in keys:
        entity_def = entity_defs.get(key.cityentity_id, {})
        chain = entity_def.get("components", {}).get("AllAge", {}).get("chain", {})
        chain_id = chain.get("chainId")
        if not isinstance(chain_id, str):
            continue
        bonuses = chain.get("config", {}).get("bonuses")
        if isinstance(bonuses, list):
            chain_pieces[chain_id].append(key)
        else:
            chain_mains[chain_id].append(key)
    return chain_mains, chain_pieces


def build_rows(
    counts: Counter[EntityKey],
    entity_defs: Dict[str, Dict[str, Any]],
    name_by_id: Dict[str, str],
) -> List[ReportRow]:
    ordered_keys = sorted(
        counts,
        key=lambda key: (name_by_id.get(key.cityentity_id, key.cityentity_id), key.level, key.entity_type),
    )
    chain_mains, chain_pieces = determine_chain_roles(ordered_keys, entity_defs)

    chain_additions: DefaultDict[EntityKey, Decimal] = defaultdict(Decimal)
    chain_notes: DefaultDict[EntityKey, List[str]] = defaultdict(list)
    chain_piece_keys: set[EntityKey] = set()

    for chain_id, pieces in chain_pieces.items():
        mains = chain_mains.get(chain_id, [])
        if len(mains) != 1:
            continue
        main_key = mains[0]
        for piece_key in pieces:
            piece_def = entity_defs.get(piece_key.cityentity_id, {})
            piece_fp, _ = summarize_chain_piece(piece_def)
            piece_count = counts[piece_key]
            chain_piece_keys.add(piece_key)
            if piece_fp <= 0:
                continue
            added = piece_fp * piece_count
            chain_additions[main_key] += added
            piece_name = name_by_id.get(piece_key.cityentity_id, piece_key.cityentity_id)
            chain_notes[main_key].append(f"chain bonus from {piece_count}x {piece_name}: {format_decimal(added)} FP")

    rows: List[ReportRow] = []
    for key in ordered_keys:
        age_code, era_name = AGE_BY_LEVEL.get(key.level, (f"L{key.level}", ""))
        entity_def = entity_defs.get(key.cityentity_id, {})
        name = entity_def.get("name", key.cityentity_id)

        production = None
        passive_boost, passive_text = summarize_passive_fp_boost(entity_def, era_name)
        if era_name:
            production = summarize_production_component(entity_def, era_name, name_by_id)
            if production is None:
                production = summarize_entity_level_production(entity_def, era_name)
            if production is None:
                production = summarize_available_products(entity_def)
            if production is None and key in chain_piece_keys:
                chain_id = entity_def.get("components", {}).get("AllAge", {}).get("chain", {}).get("chainId")
                mains = chain_mains.get(str(chain_id), [])
                if len(mains) == 1:
                    main_name = name_by_id.get(mains[0].cityentity_id, mains[0].cityentity_id)
                    piece_fp, _ = summarize_chain_piece(entity_def)
                    if piece_fp > 0:
                        production = (
                            f"chain contribution to {main_name}: {format_decimal(piece_fp)} FP each "
                            "(counted on main building)"
                        )
            if production is None and passive_text is not None:
                production = passive_text
            elif production is not None and passive_text is not None:
                production = production + "; " + passive_text

        if production is None:
            production = "no production found in input/ref/zpwd-ref for this age"

        if key in chain_additions:
            production = production + "; " + "; ".join(chain_notes[key])

        rows.append(
            ReportRow(
                key=key,
                name=str(name),
                age_code=age_code,
                count=counts[key],
                passive_fp_boost=passive_boost,
                production=production,
            )
        )
    return rows


def format_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return str(int(value))
    return format(value.normalize(), "f")


def option_base_fp(option_text: str) -> Decimal:
    total = Decimal("0")
    for part in [fragment.strip() for fragment in option_text.split(";") if fragment.strip()]:
        if "random:" in part:
            for probability_text, fp_text in re.findall(r"([0-9]+(?:\.[0-9]+)?)%\s+(\d+)\s+FP\b", part):
                probability = Decimal(probability_text) / Decimal("100")
                total += probability * Decimal(fp_text)
        else:
            for fp_text in re.findall(r"(\d+)\s+FP\b", part):
                total += Decimal(fp_text)
    return total


def base_expected_fp(production: str) -> Decimal:
    options = [option.strip() for option in production.split("|") if option.strip()]
    if not options:
        return Decimal("0")
    return max((option_base_fp(option) for option in options), default=Decimal("0"))


def write_average_expected_fp_report(rows: Sequence[ReportRow], output_path: Path) -> None:
    total_passive = sum((row.passive_fp_boost * row.count for row in rows), Decimal("0"))
    multiplier = Decimal("1") + (total_passive / Decimal("100"))

    sortable: List[Dict[str, Any]] = []
    for row in rows:
        base_fp = Decimal("0") if "chain contribution to " in row.production else base_expected_fp(row.production)
        average_fp = (base_fp * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        sortable.append(
            {
                "AverageExpectedFP": str(int(average_fp)),
                "BaseFP": format_decimal(base_fp),
                "Name": row.name,
                "Level": row.key.level,
                "Age": row.age_code,
                "Count": row.count,
                "PassiveFPBoost": format_decimal(row.passive_fp_boost),
                "Production": row.production,
                "_sort_average_fp": average_fp,
                "_sort_base_fp": base_fp,
            }
        )

    sortable.sort(
        key=lambda row: (-row["_sort_average_fp"], -row["_sort_base_fp"], row["Name"], row["Level"])
    )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES_AVERAGE_FP, delimiter="\t")
        writer.writeheader()
        for row in sortable:
            row.pop("_sort_average_fp")
            row.pop("_sort_base_fp")
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    reference_path = Path(__file__).resolve().parents[1] / "input" / "ref" / "zpwd-ref"
    input_dir = base_dir / "input"
    explicit_input = args.map_file is not None
    map_file = args.map_file if args.map_file is not None else default_map_path(input_dir)
    map_data = load_json(map_file)
    reference_data = load_json(reference_path)
    entity_defs, name_by_id = build_entity_index(reference_data)
    counts = collect_map_entries(map_data)
    rows = build_rows(counts, entity_defs, name_by_id)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = args.output_dir / (
        f"{output_basename(map_file)}_buildings_level_age_production_sorted_by_average_expected_fp.tsv"
    )
    write_average_expected_fp_report(rows, tsv_path)
    if explicit_input:
        return
    convert_tsv_to_excel(tsv_path)
    tsv_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
