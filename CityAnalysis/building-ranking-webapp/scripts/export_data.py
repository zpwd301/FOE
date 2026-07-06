#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT_DIR = os.path.join(PROJECT_ROOT, "script")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import building_attribute_ranking_workbook as model  # noqa: E402


DEFAULT_AGE = "VirtualFuture"


def record_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    area = record.get("area")
    return {
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
        }
    return out


def main() -> None:
    reference_file = os.path.abspath(model.DEFAULT_REFERENCE)
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

    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "ranking-data.js")
    with open(out_file, "w", encoding="utf-8") as handle:
        handle.write("window.FOE_BUILDING_RANKING_DATA = ")
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write(";\n")
    print(f"Wrote {os.path.relpath(out_file, PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
