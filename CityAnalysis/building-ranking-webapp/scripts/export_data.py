#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT_DIR = os.path.join(PROJECT_ROOT, "script")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import building_ranking_model as model  # noqa: E402

DEFAULT_AGE = "VirtualFuture"
DATA_PREFIX = "window.FOE_BUILDING_RANKING_DATA = "
# Increment when the serialized website payload shape or semantics change.
EXPORT_SCHEMA_VERSION = 3


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
        "script": os.path.join(data_dir, "ranking-data.js"),
        "compressed": os.path.join(data_dir, "ranking-data.json.gz"),
        "state": os.path.join(data_dir, "export-state.json"),
    }


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


def semantic_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(data.get("metadata", {}))
    metadata.pop("generatedAt", None)
    return {**data, "metadata": metadata}


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
    if not all(os.path.exists(paths[key]) for key in ("script", "compressed", "state")):
        return False
    try:
        with open(paths["state"], "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return False
    return (
        all(state.get(key) == value for key, value in fingerprint.items())
        and state.get("scriptSha256") == file_sha256(paths["script"])
        and state.get("compressedSha256") == file_sha256(paths["compressed"])
    )


def write_export_state(fingerprint: Dict[str, Any]) -> None:
    paths = data_paths()
    state = {
        **fingerprint,
        "scriptSha256": file_sha256(paths["script"]),
        "compressedSha256": file_sha256(paths["compressed"]),
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
        "category": model.building_category_label(str(record["entity_id"])),
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


def write_data_files(data: Dict[str, Any]) -> bool:
    paths = data_paths()
    out_dir = paths["directory"]
    json_text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(paths["script"]):
        try:
            existing_json_text, existing_data = read_wrapped_data(paths["script"])
        except (OSError, ValueError, json.JSONDecodeError):
            existing_json_text, existing_data = "", {}
        if semantic_payload(existing_data) == semantic_payload(data):
            expected_compressed = gzip.compress(existing_json_text.encode("utf-8"), compresslevel=9, mtime=0)
            repaired = not os.path.exists(paths["compressed"]) or file_sha256(paths["compressed"]) != hashlib.sha256(expected_compressed).hexdigest()
            if repaired:
                atomic_write(paths["compressed"], expected_compressed, binary=True)
                print(f"Repaired {os.path.relpath(paths['compressed'], PROJECT_ROOT)}")
            print("No ranking changes; kept the existing data files and generation timestamp.")
            return False

    script_text = f"{DATA_PREFIX}{json_text};\n"
    compressed_bytes = gzip.compress(json_text.encode("utf-8"), compresslevel=9, mtime=0)
    atomic_write(paths["script"], script_text)
    atomic_write(paths["compressed"], compressed_bytes, binary=True)

    script_size = os.path.getsize(paths["script"])
    compressed_size = os.path.getsize(paths["compressed"])
    print(f"Wrote {os.path.relpath(paths['script'], PROJECT_ROOT)} ({script_size:,} bytes)")
    print(f"Wrote {os.path.relpath(paths['compressed'], PROJECT_ROOT)} ({compressed_size:,} bytes)")
    return True


def compress_existing_data() -> None:
    paths = data_paths()
    json_text, _ = read_wrapped_data(paths["script"])
    atomic_write(
        paths["compressed"],
        gzip.compress(json_text.encode("utf-8"), compresslevel=9, mtime=0),
        binary=True,
    )
    print(f"Wrote {os.path.relpath(paths['compressed'], PROJECT_ROOT)} ({os.path.getsize(paths['compressed']):,} bytes)")


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
        help="Create the compressed JSON asset from the current ranking-data.js without rebuilding data.",
    )
    args = parser.parse_args()
    if args.compress_existing:
        compress_existing_data()
    else:
        main()
