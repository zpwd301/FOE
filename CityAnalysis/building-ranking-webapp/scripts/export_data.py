#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT_DIR = os.path.join(PROJECT_ROOT, "script")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import building_ranking_model as model  # noqa: E402

DEFAULT_AGE = "SpaceAgeAsteroidBelt"
DATA_PREFIX = "window.FOE_BUILDING_RANKING_DATA = "
# Increment when the serialized website payload shape or semantics change.
EXPORT_SCHEMA_VERSION = 7


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_paths() -> Dict[str, str]:
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    return {
        "directory": data_dir,
        "core": os.path.join(data_dir, "ranking-core.json"),
        "coreCompressed": os.path.join(data_dir, "ranking-core.json.gz"),
        "ages": os.path.join(data_dir, "ages"),
        "legacyScript": os.path.join(data_dir, "ranking-data.js"),
        "legacyCompressed": os.path.join(data_dir, "ranking-data.json.gz"),
        "state": os.path.join(data_dir, "export-state.json"),
    }


def age_data_paths(age: str) -> Dict[str, str]:
    directory = data_paths()["ages"]
    return {
        "json": os.path.join(directory, f"{age}.json"),
        "compressed": os.path.join(directory, f"{age}.json.gz"),
    }


def index_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "index.html")


def data_version() -> str:
    paths = data_paths()
    digest = hashlib.sha256()
    digest.update(file_sha256(paths["coreCompressed"]).encode("ascii"))
    for age in model.AGE_ORDER:
        digest.update(file_sha256(age_data_paths(age)["compressed"]).encode("ascii"))
    return digest.hexdigest()[:12]


def index_data_version() -> str:
    with open(index_path(), "r", encoding="utf-8") as handle:
        match = re.search(r'data-data-version="([^"]+)"', handle.read())
    return match.group(1) if match else ""


def update_index_data_version(version: str) -> None:
    path = index_path()
    with open(path, "r", encoding="utf-8") as handle:
        current = handle.read()
    updated, count = re.subn(
        r'data-data-version="[^"]+"',
        f'data-data-version="{version}"',
        current,
        count=1,
    )
    if count != 1:
        raise ValueError("data-data-version was not found exactly once in index.html")
    if updated != current:
        atomic_write(path, updated)
        print(f"Updated the dashboard data cache version to {version}.")


def atomic_write(path: str, content: Any, binary: bool = False) -> None:
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile(mode, dir=os.path.dirname(path), delete=False, **kwargs) as handle:
        temp_path = handle.name
        handle.write(content)
    os.replace(temp_path, path)


def read_wrapped_data(path: str) -> tuple[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        script_text = handle.read()
    if not script_text.startswith(DATA_PREFIX) or not script_text.rstrip().endswith(";"):
        raise ValueError(f"Unexpected data wrapper in {path}")
    json_text = script_text[len(DATA_PREFIX):].rstrip()[:-1]
    return json_text, json.loads(json_text)


def export_fingerprint(reference_file: str) -> Dict[str, Any]:
    return {
        "schemaVersion": EXPORT_SCHEMA_VERSION,
        "modelVersion": model.WORKBOOK_VERSION,
        "modelSha256": file_sha256(os.path.abspath(model.__file__)),
        "exporterSha256": file_sha256(os.path.abspath(__file__)),
        "source": os.path.relpath(reference_file, PROJECT_ROOT),
        "sourceSha256": file_sha256(reference_file),
    }


def matching_export_state(fingerprint: Dict[str, Any]) -> bool:
    paths = data_paths()
    if not all(os.path.exists(paths[key]) for key in ("core", "coreCompressed", "state")):
        return False
    try:
        with open(paths["state"], "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return False
    if not all(state.get(key) == value for key, value in fingerprint.items()):
        return False
    if state.get("coreSha256") != file_sha256(paths["core"]):
        return False
    if state.get("coreCompressedSha256") != file_sha256(paths["coreCompressed"]):
        return False
    age_assets = state.get("ageAssets")
    if not isinstance(age_assets, dict) or set(age_assets) != set(model.AGE_ORDER):
        return False
    for age in model.AGE_ORDER:
        age_paths = age_data_paths(age)
        if not all(os.path.exists(age_paths[key]) for key in ("json", "compressed")):
            return False
        if age_assets[age].get("sha256") != file_sha256(age_paths["json"]):
            return False
        if age_assets[age].get("compressedSha256") != file_sha256(age_paths["compressed"]):
            return False
    current_version = data_version()
    if state.get("dataVersion") != current_version:
        return False
    if index_data_version() != current_version:
        update_index_data_version(current_version)
    return True


def write_export_state(fingerprint: Dict[str, Any]) -> None:
    paths = data_paths()
    version = data_version()
    update_index_data_version(version)
    age_assets = {}
    for age in model.AGE_ORDER:
        age_paths = age_data_paths(age)
        age_assets[age] = {
            "sha256": file_sha256(age_paths["json"]),
            "compressedSha256": file_sha256(age_paths["compressed"]),
        }
    state = {
        **fingerprint,
        "coreSha256": file_sha256(paths["core"]),
        "coreCompressedSha256": file_sha256(paths["coreCompressed"]),
        "ageAssets": age_assets,
        "dataVersion": version,
    }
    atomic_write(paths["state"], json.dumps(state, indent=2, sort_keys=True) + "\n")


def record_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    area = record.get("area")
    payload = {
        "entityId": record["entity_id"],
        "name": record["name"],
        "type": record.get("type", ""),
        "selectedAge": record.get("selected_age", ""),
        "available": record.get("available", ""),
        "size": record.get("size", ""),
        "area": area,
        "adjustedArea": model.adjusted_area(record),
        "requiresRoad": model.require_road_connection_label(record) == "Y",
        "category": model.building_category_label(
            str(record["entity_id"]),
            str(record.get("name", "")),
        ),
        "environmentEffect": record.get("environment_effect", ""),
        "rewardProduction": record.get("reward_production", ""),
        "attrs": {
            key: value
            for key, value in sorted(record.get("attrs", {}).items())
            if abs(float(value)) > 1e-12
        },
    }
    return payload


def age_variant_index(
    records_by_age: Dict[str, List[Dict[str, Any]]],
    field: str,
    expected_type: type,
) -> Dict[str, Dict[str, Any]]:
    variants_by_entity: Dict[str, Dict[str, Any]] = {}
    for age, records in records_by_age.items():
        for record in records:
            entity_id = str(record["entity_id"])
            value = record.get(field)
            if not isinstance(value, expected_type):
                value = expected_type()
            variants_by_entity.setdefault(entity_id, {})[age] = value

    index: Dict[str, Dict[str, Any]] = {}
    for entity_id, values_by_age in variants_by_entity.items():
        if not any(values_by_age.values()):
            continue
        grouped: Dict[str, Dict[str, Any]] = {}
        for age, value in values_by_age.items():
            token = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            group = grouped.setdefault(token, {"value": value, "ages": []})
            group["ages"].append(age)
        default_group = max(grouped.values(), key=lambda group: len(group["ages"]))
        default_value = default_group["value"]
        overrides = {
            age: value
            for age, value in values_by_age.items()
            if value != default_value
        }
        entry: Dict[str, Any] = {"default": default_value}
        if overrides:
            entry["overrides"] = overrides
        index[entity_id] = entry
    return index


def kit_production_index(records_by_age: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    return age_variant_index(records_by_age, "kit_production", dict)


def fragment_reward_index(records_by_age: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    return age_variant_index(records_by_age, "fragment_rewards", list)


def unit_production_index(records_by_age: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    return age_variant_index(records_by_age, "unit_production", list)


def attr_metadata(attr_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key in attr_keys:
        out[key] = {
            "label": model.attr_label(key),
            "overallLabel": model.overall_ranking_attr_label(key),
            "description": model.attr_description(key),
            "direction": model.direction_for_attr(key),
            "defaultWeight": model.default_weight_for_attr(key),
            "overallGroup": model.overall_weight_group_for_attr(key),
            "isFighting": model.is_fighting_attr(key),
            "isGbg": model.is_guild_battleground_fighting_attr(key),
            "isGe": model.is_guild_expedition_fighting_attr(key),
            "isRed": model.is_red_fighting_attr(key),
            "isBlue": model.is_blue_fighting_attr(key),
            "isAttack": model.is_attack_fighting_attr(key),
            "isDefense": model.is_defense_fighting_attr(key),
            "isQiBlue": model.is_qi_blue_fighting_attr(key),
            "isQiRed": model.is_qi_red_fighting_attr(key),
            "isQi": model.is_qi_attr(key),
            "isRoad": model.is_road_connection_attr_key(key),
            "isSignedCentered": key in model.SIGNED_CENTERED_ATTRS,
            "isGoodsTotalComponent": key in model.OVERALL_GOODS_TOTAL_COMPONENT_ATTRS,
            "isOverallQiStart": key in model.OVERALL_QI_START_ATTRS,
            "isForcedZero": model.is_forced_zero_weight_attr(key),
            "isKit": key in model.KIT_ATTR_TO_FAMILY,
            "kitFamily": model.KIT_ATTR_TO_FAMILY.get(key, ""),
        }
    return out


def split_data(data: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    records_by_age = data.get("recordsByAge")
    if not isinstance(records_by_age, dict) or not records_by_age:
        raise ValueError("recordsByAge is missing from the ranking payload")
    core = {key: value for key, value in data.items() if key != "recordsByAge"}
    return core, records_by_age


def compressed_json(data: Any) -> tuple[str, bytes]:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text, gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)


def write_data_files(data: Dict[str, Any]) -> None:
    paths = data_paths()
    core, records_by_age = split_data(data)
    if set(records_by_age) != set(model.AGE_ORDER):
        missing = sorted(set(model.AGE_ORDER) - set(records_by_age))
        extra = sorted(set(records_by_age) - set(model.AGE_ORDER))
        raise ValueError(f"Age payload mismatch; missing={missing}, extra={extra}")
    core_text, core_compressed = compressed_json(core)
    atomic_write(paths["core"], core_text + "\n")
    atomic_write(paths["coreCompressed"], core_compressed, binary=True)

    expected_age_files = set()
    total_age_json = 0
    total_age_compressed = 0
    for age, records in records_by_age.items():
        if age not in model.AGE_ORDER:
            continue
        age_paths = age_data_paths(age)
        age_payload = {"age": age, "records": records}
        age_text, age_compressed = compressed_json(age_payload)
        atomic_write(age_paths["json"], age_text + "\n")
        atomic_write(age_paths["compressed"], age_compressed, binary=True)
        expected_age_files.update(age_paths.values())
        total_age_json += len(age_text.encode("utf-8")) + 1
        total_age_compressed += len(age_compressed)

    if os.path.isdir(paths["ages"]):
        for filename in os.listdir(paths["ages"]):
            candidate = os.path.join(paths["ages"], filename)
            if os.path.isfile(candidate) and candidate not in expected_age_files:
                os.remove(candidate)

    for legacy_key in ("legacyScript", "legacyCompressed"):
        if os.path.exists(paths[legacy_key]):
            os.remove(paths[legacy_key])

    print(
        "Wrote split ranking data: "
        f"core {len(core_text.encode('utf-8')) + 1:,} bytes JSON / {len(core_compressed):,} bytes gzip; "
        f"ages {total_age_json:,} bytes JSON / {total_age_compressed:,} bytes gzip."
    )


def compress_existing_data() -> None:
    paths = data_paths()
    if os.path.exists(paths["legacyScript"]):
        _, data = read_wrapped_data(paths["legacyScript"])
        write_data_files(data)
        write_export_state(export_fingerprint(os.path.abspath(model.DEFAULT_REFERENCE)))
        return

    with open(paths["core"], "r", encoding="utf-8") as handle:
        core = json.load(handle)
    _, core_compressed = compressed_json(core)
    atomic_write(paths["coreCompressed"], core_compressed, binary=True)
    for age in model.AGE_ORDER:
        age_paths = age_data_paths(age)
        with open(age_paths["json"], "r", encoding="utf-8") as handle:
            age_payload = json.load(handle)
        _, age_compressed = compressed_json(age_payload)
        atomic_write(age_paths["compressed"], age_compressed, binary=True)
    write_export_state(export_fingerprint(os.path.abspath(model.DEFAULT_REFERENCE)))
    print("Rebuilt compressed core and age assets from the existing JSON files.")


def main() -> None:
    reference_file = os.path.abspath(model.DEFAULT_REFERENCE)
    fingerprint = export_fingerprint(reference_file)
    if matching_export_state(fingerprint):
        print("Input, model, schema, and output hashes are unchanged; export skipped.")
        return
    payload = model.load_payload(reference_file)
    entities = payload.get("CityEntities")
    if not isinstance(entities, dict):
        raise SystemExit(f"CityEntities not found in {reference_file}")
    model.validate_building_category_corrections(entities)

    records_by_age, attr_keys = model.build_age_records(entities, list(model.AGE_ORDER), False)
    category_records = []
    seen_entity_ids = set()
    for age_records in records_by_age.values():
        for record in age_records:
            entity_id = str(record["entity_id"])
            if entity_id not in seen_entity_ids:
                category_records.append(record)
                seen_entity_ids.add(entity_id)

    data = {
        "metadata": {
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "source": os.path.relpath(reference_file, PROJECT_ROOT),
            "workbookModelVersion": model.WORKBOOK_VERSION,
            "defaultAge": DEFAULT_AGE,
        },
        "ages": [
            {"key": age, "label": model.age_display_name(age)}
            for age in model.AGE_ORDER
        ],
        "categories": model.building_category_options(category_records),
        "kitFamilies": [
            {"key": key, **definition}
            for key, definition in model.KIT_FAMILY_DEFINITIONS.items()
        ],
        "kitProductionByEntity": kit_production_index(records_by_age),
        "unitProductionByEntity": unit_production_index(records_by_age),
        "fragmentRewardsByEntity": fragment_reward_index(records_by_age),
        "attrKeys": attr_keys,
        "attrs": attr_metadata(attr_keys),
        "constants": {
            "prodFpAttr": model.PROD_FP_ATTR,
            "prodGoodsAttr": model.PROD_GOODS_ATTR,
            "prodGuildGoodsAttr": model.PROD_GUILD_GOODS_ATTR,
            "prodMedalsAttr": model.PROD_MEDALS_ATTR,
            "boostFpAttr": model.BOOST_FP_ATTR,
            "boostGoodsAttr": model.BOOST_GOODS_ATTR,
            "boostSpecialGoodsAttr": model.BOOST_SPECIAL_GOODS_ATTR,
            "boostGuildGoodsAttr": model.BOOST_GUILD_GOODS_ATTR,
            "boostMedalsAttr": model.BOOST_MEDALS_ATTR,
            "netHappinessAttr": model.NET_HAPPINESS_ATTR,
            "overallFightingBudget": model.OVERALL_FIGHTING_WEIGHT_BUDGET,
            "overallNonFightingBudget": model.OVERALL_NON_FIGHTING_WEIGHT_BUDGET,
            "overallFightingSubgroupBudgets": model.OVERALL_FIGHTING_SUBGROUP_BUDGETS,
            "overallGbgGeCombinedBudget": model.OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET,
            "overallQiStartRawWeight": model.OVERALL_QI_START_RAW_WEIGHT,
            "fightingCurrentNextUnitCombinedRawWeight": model.FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT,
            "fightingGbgGeCombinedRawWeight": model.FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT,
            "fightingWeightScale": model.DEFAULT_FIGHTING_WEIGHT_SCALE,
            "farmingFpGoodsCombinedRawWeight": model.FARMING_FP_GOODS_COMBINED_RAW_WEIGHT,
            "farmingSecondaryRawWeights": model.FARMING_SECONDARY_RAW_WEIGHTS,
        },
        "defaults": {
            "estimatedFpProduction": model.DEFAULT_ESTIMATED_FP_PRODUCTION,
            "estimatedGoodsProduction": model.DEFAULT_ESTIMATED_GOODS_PRODUCTION,
            "estimatedGuildGoodsProduction": model.DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION,
            "estimatedMedalProduction": model.DEFAULT_ESTIMATED_MEDAL_PRODUCTION,
            "estimatedSpecialGoodsProduction": model.DEFAULT_ESTIMATED_SPECIAL_GOODS_PRODUCTION,
            "fightingGbgGeFocus": model.DEFAULT_FIGHTING_GBG_GE_FOCUS,
            "fightingRedBlueFocus": model.DEFAULT_FIGHTING_RED_BLUE_FOCUS,
            "fightingAttackDefenseFocus": model.DEFAULT_FIGHTING_ATTACK_DEFENSE_FOCUS,
            "fightingUnitAgeFocus": model.DEFAULT_FIGHTING_UNIT_AGE_FOCUS,
            "productionFpGoodsFocus": model.DEFAULT_PRODUCTION_FP_GOODS_FOCUS,
            "qiFighterRole": "Both",
        },
        "recordsByAge": {
            age: [record_payload(record) for record in records]
            for age, records in records_by_age.items()
        },
    }

    write_data_files(data)
    write_export_state(fingerprint)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export the building-ranking dashboard data.")
    parser.add_argument(
        "--compress-existing",
        action="store_true",
        help="Migrate legacy data or rebuild compressed core and age assets without rebuilding the model.",
    )
    args = parser.parse_args()
    if args.compress_existing:
        compress_existing_data()
    else:
        main()
