#!/usr/bin/env python3
"""Build a configurable building ranking workbook from reference CityEntities."""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DEFAULT_REFERENCE = os.path.join(INPUT_DIR, "ref", "zpwd-ref")
EVENT_COLOR_MAP_FILE = os.path.join(INPUT_DIR, "event_color_map.json")

AGE_BY_LEVEL = {
    0: "StoneAge",
    1: "BronzeAge",
    2: "IronAge",
    3: "EarlyMiddleAge",
    4: "HighMiddleAge",
    5: "LateMiddleAge",
    6: "ColonialAge",
    7: "IndustrialAge",
    8: "ProgressiveEra",
    9: "ModernEra",
    10: "PostModernEra",
    11: "ContemporaryEra",
    12: "TomorrowEra",
    13: "FutureEra",
    14: "ArcticFuture",
    15: "OceanicFuture",
    16: "VirtualFuture",
    17: "SpaceAgeMars",
    18: "SpaceAgeAsteroidBelt",
    19: "SpaceAgeVenus",
    20: "SpaceAgeJupiterMoon",
    21: "SpaceAgeTitan",
    22: "SpaceAgeSpaceHub",
}
AGE_ORDER = {age: idx for idx, age in AGE_BY_LEVEL.items()}

WEIGHT_HEADER_ROW = 8
WEIGHT_START_ROW = WEIGHT_HEADER_ROW + 1
BUILDING_HEADER_ROW = 10
BUILDING_DATA_START_ROW = BUILDING_HEADER_ROW + 1
RAW_START_COLUMN = 7
FIGHTING_TOP_N = 100
OVERALL_TOP_N = 200
REQUIRE_ROAD_HEADER = "Require Road Connection"
OVERALL_RANKING_SHEET = "Overall Ranking"
OVERALL_SOURCE_SHEET = "Overall Ranking Source"
OVERALL_SCORE_SHEET = "Overall Scores"
OVERALL_EFFICIENCY_SHEET = "Overall Efficiency Ranking"
FIGHTING_SCORE_SHEET = "Fighting Scores"
FIGHTING_EFFICIENCY_SHEET = "Fighting Efficiency Ranking"
FP_GOODS_SCORE_SHEET = "Farming Scores"
FP_GOODS_PRODUCTION_SHEET = "Farming Ranking (WIP)"
FP_GOODS_EFFICIENCY_SHEET = "Farming Efficiency (WIP)"
QI_SCORE_SHEET = "QI Scores"
QI_RANKING_SHEET = "QI Ranking"
QI_EFFICIENCY_SHEET = "QI Efficiency Ranking"
CONTROLS_SHEET = "Main Controls"
ADVANCED_CONTROLS_SHEET = "Advanced Controls"
AGE_OPTIONS_SHEET = "Age Options"
CATEGORY_OPTIONS_SHEET = "Category Options"
AGE_DATA_SHEET = "Age Data"
GOODS_RESOURCE_AUDIT_SHEET = "Goods Resource Audit"
CONTROLS_SHEET_REF = f"'{CONTROLS_SHEET}'"
ADVANCED_CONTROLS_SHEET_REF = f"'{ADVANCED_CONTROLS_SHEET}'"
AGE_DATA_SHEET_REF = f"'{AGE_DATA_SHEET}'"
XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
# Increment this version before each pushed code change to this workbook generator.
WORKBOOK_VERSION = "1.0.42"
DEFAULT_ESTIMATED_FP_PRODUCTION = 30000.0
DEFAULT_ESTIMATED_GOODS_PRODUCTION = 20000.0
DEFAULT_ESTIMATED_SPECIAL_GOODS_PRODUCTION = 120.0
DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION = 20000.0
DEFAULT_ESTIMATED_MEDAL_PRODUCTION = 400000.0
DEFAULT_FIGHTING_GBG_GE_FOCUS = 2
DEFAULT_FIGHTING_RED_BLUE_FOCUS = 3
DEFAULT_FIGHTING_UNIT_AGE_FOCUS = 3
DEFAULT_FIGHTING_ATTACK_DEFENSE_FOCUS = 2
DEFAULT_PRODUCTION_FP_GOODS_FOCUS = 2
FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT = 0.5
FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT = 3.0
DEFAULT_FIGHTING_WEIGHT_SCALE = 60.0 / 9.5
OVERALL_FIGHTING_WEIGHT_BUDGET = 30.0
OVERALL_NON_FIGHTING_WEIGHT_BUDGET = 30.0
OVERALL_TOTAL_WEIGHT_CELL = "$B$6"
FIGHTING_TOTAL_WEIGHT_CELL = "$C$6"
FP_GOODS_TOTAL_WEIGHT_CELL = "$E$6"
QI_TOTAL_WEIGHT_CELL = "$G$6"
ESTIMATED_FP_PRODUCTION_CELL = "$B$6"
ESTIMATED_GOODS_PRODUCTION_CELL = "$B$7"
ESTIMATED_GUILD_GOODS_PRODUCTION_CELL = "$B$8"
ESTIMATED_MEDAL_PRODUCTION_CELL = "$B$9"
ESTIMATED_SPECIAL_GOODS_PRODUCTION_CELL = "$B$11"
CITY_AGE_CELL = "$B$3"
CITY_AGE_LIST_NAME = "CityAgeList"
BUILDING_CATEGORY_FILTER_CELL = "$B$5"
BUILDING_CATEGORY_LIST_NAME = "BuildingCategoryList"
ALL_BUILDING_CATEGORIES = "All Building Categories"
QI_FIGHTER_ROLE_CELL = "$B$10"
FIGHTING_GBG_GE_FOCUS_CELL = "$B$13"
FIGHTING_RED_BLUE_FOCUS_CELL = "$B$15"
FIGHTING_ATTACK_DEFENSE_FOCUS_CELL = "$B$17"
FIGHTING_UNIT_AGE_FOCUS_CELL = "$B$19"
PRODUCTION_FP_GOODS_FOCUS_CELL = "$B$21"
OVERALL_RAW_WEIGHT_COLUMN = 14
OVERALL_WEIGHT_GROUP_COLUMN = 15
OVERALL_WEIGHT_BUDGET_COLUMN = 16
OVERALL_WEIGHT_OVERRIDE_COLUMN = 17
FIGHTING_WEIGHT_OVERRIDE_COLUMN = 18
FP_GOODS_WEIGHT_OVERRIDE_COLUMN = 19
QI_WEIGHT_OVERRIDE_COLUMN = 20
ADVANCED_WEIGHT_MODE_CELL = "$B$7"
NET_HAPPINESS_ATTR = "net_happiness"
OVERALL_FIGHTING_WEIGHT_GROUP = "Fighting"
OVERALL_NON_FIGHTING_WEIGHT_GROUP = "Non-Fighting"
OVERALL_FIGHTING_ALL_WEIGHT_GROUP = "Fighting: All"
OVERALL_FIGHTING_GBG_WEIGHT_GROUP = "Fighting: GBG"
OVERALL_FIGHTING_GE_WEIGHT_GROUP = "Fighting: GE"
OVERALL_FIGHTING_QI_WEIGHT_GROUP = "Fighting: QI"
OVERALL_FIGHTING_UNITS_WEIGHT_GROUP = "Fighting: Units"
OVERALL_FIGHTING_SUBGROUP_BUDGETS = {
    OVERALL_FIGHTING_ALL_WEIGHT_GROUP: 10.0,
    OVERALL_FIGHTING_GBG_WEIGHT_GROUP: 4.5,
    OVERALL_FIGHTING_GE_WEIGHT_GROUP: 4.5,
    OVERALL_FIGHTING_QI_WEIGHT_GROUP: 6.0,
    OVERALL_FIGHTING_UNITS_WEIGHT_GROUP: 5.0,
}
OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET = (
    OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GBG_WEIGHT_GROUP]
    + OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GE_WEIGHT_GROUP]
)
OVERALL_GOODS_TOTAL_COMPONENT_ATTRS = {
    "prod_resource_all_goods_of_previous_age",
    "prod_resource_all_goods_of_age",
    "prod_resource_all_goods_of_next_age",
    "prod_resource_random_good",
    "prod_resource_special_goods_up_to_age",
}
OVERALL_QI_START_ATTRS = {
    "boost_guild_raids_coins_start_all",
    "boost_guild_raids_goods_start_all",
    "boost_guild_raids_units_start_all",
}
OVERALL_QI_START_RAW_WEIGHT = 0.25
SIGNED_CENTERED_ATTRS = {
    NET_HAPPINESS_ATTR,
    "happiness_demanded",
    "static_happiness",
    "static_population",
}
HIDDEN_ZERO_WEIGHT_ADVANCED_CONTROL_LABELS = {
    "Autopolivatepriority Priority",
    "Boost: Coin production percentage",
    "Boost: Forge points production percentage",
    "Boost: Goods production percentage",
    "Boost: Guild goods production percentage",
    "Boost: Medal production percentage",
    "Boost: Special goods production percentage",
    "Boost: Supply production percentage",
    "Gross Happiness",
    "Happiness Demand",
    "Limited Config Collectionamount",
    "Limited Config Expire Time (days)",
    "Multiplycollection Chance",
    "Multiplycollection Charges",
    "Multiplycollection Factor",
}


def is_forced_zero_weight_attr(key: str) -> bool:
    return attr_label(key) in HIDDEN_ZERO_WEIGHT_ADVANCED_CONTROL_LABELS


BOOST_FP_ATTR = "boost_forge_points_production_all"
BOOST_GOODS_ATTR = "boost_goods_production_all"
BOOST_SPECIAL_GOODS_ATTR = "boost_special_goods_production_all"
BOOST_GUILD_GOODS_ATTR = "boost_guild_goods_production_all"
BOOST_MEDALS_ATTR = "boost_medal_production_all"
PROD_FP_ATTR = "prod_resource_strategy_points"
PROD_GOODS_ATTR = "prod_resource_goods_total"
PROD_GUILD_GOODS_ATTR = "prod_resource_guild_goods"
PROD_MEDALS_ATTR = "prod_resource_medals"
FARMING_FP_GOODS_COMBINED_RAW_WEIGHT = 40.0
FARMING_SECONDARY_RAW_WEIGHTS = {
    PROD_MEDALS_ATTR: 5.0,
    NET_HAPPINESS_ATTR: 1.0,
    "prod_resource_blueprint": 5.0,
    "prod_resource_premium": 5.0,
    "prod_resource_supplies": 4.0,
}
FARMING_RANKING_ABOUT_NOTE = (
    "Farming Ranking (WIP) uses 40 default weight points split between FPs and Goods Total by the Production FP/Goods focus, plus 20 points across medals, net happiness, blueprints, diamonds, and supplies. Net happiness is intentionally lower than the other secondary farming weights. "
    "The default farming ranking profile remains, with great dignity and very little closure, a work in progress. Inno’s goods production system appears to contain an infinite number of attributes and exceptions against spreadsheet stability. My current lack of motivation to age out of VF has also contributed exactly nothing to the validation effort. Additionally, the current preset weight profile may be somewhat diamond-heavy for a standard city, so please interpret it as a technical preview, and take this as an excellent opportunity to explore the Farming Override column in the Advanced Controls. 😅"
)
GBG_REWARD_PREFIX = "W_MultiAge_GBG"
QI_REWARD_PREFIX = "W_MultiAge_GR"
GE_REWARD_PREFIXES = ("W_MultiAge_Expedition", "W_MultiAge_GEX")
MULTI_AGE_PREFIX = "W_MultiAge_"
REWARD_GROUP_COLORS = {
    "GBG": "C6E0B4",
    "QI": "9DC3E6",
    "GE": "F4B183",
}
EVENT_REWARD_COLORS = [
    "F4CCCC",
    "B4A7D6",
    "76A5AF",
    "D9D2E9",
    "D5A6BD",
    "FFD966",
    "A9D18E",
    "8EA9DB",
    "F8CBAD",
    "A2C4C9",
    "C27BA0",
    "E69138",
]

TAB_COLORS = {
    CONTROLS_SHEET: "5B9BD5",
    ADVANCED_CONTROLS_SHEET: "1F4E78",
    OVERALL_RANKING_SHEET: "9DC3E6",
    OVERALL_SCORE_SHEET: "9DC3E6",
    OVERALL_EFFICIENCY_SHEET: "5B9BD5",
    FIGHTING_SCORE_SHEET: "F4B183",
    "Fighting Ranking": "F4B183",
    FIGHTING_EFFICIENCY_SHEET: "C65911",
    FP_GOODS_SCORE_SHEET: "A9D18E",
    FP_GOODS_PRODUCTION_SHEET: "A9D18E",
    FP_GOODS_EFFICIENCY_SHEET: "548235",
    QI_SCORE_SHEET: "B4A7D6",
    QI_RANKING_SHEET: "B4A7D6",
    QI_EFFICIENCY_SHEET: "7030A0",
    AGE_OPTIONS_SHEET: "A6A6A6",
    CATEGORY_OPTIONS_SHEET: "A6A6A6",
    AGE_DATA_SHEET: "A6A6A6",
    "About": "A6A6A6",
}

TITLE_FILL_COLOR = "D6EAF7"
TITLE_FONT_COLOR = "243447"
HEADER_FILL_COLOR = "E7F4DC"
HEADER_FONT_COLOR = "243447"
BORDER_COLOR = "C7D6E2"
EDITABLE_FILL_COLOR = "FFF4CC"
CONTROL_CONTEXT_FILL_COLOR = "E4F3EA"
SLIDER_FILL_COLOR = HEADER_FILL_COLOR
SLIDER_SELECTED_FILL_COLOR = "B7D7F0"

CORE_RESOURCES = {
    "clan_power",
    "coins",
    "copper_coins",
    "diamonds",
    "diplomacy",
    "happiness",
    "medals",
    "money",
    "population",
    "premium",
    "ranking_points",
    "satisfaction",
    "social_interaction",
    "strategy_points",
    "supplies",
}

RESOURCE_ATTR_ALIASES = {
    "each_special_goods_up_to_age": "special_goods_up_to_age",
    "random_good_of_age": "all_goods_of_age",
    "random_good_of_next_age": "all_goods_of_next_age",
    "random_good_of_previous_age": "all_goods_of_previous_age",
    "random_special_good_up_to_age": "special_goods_up_to_age",
}

AGGREGATE_GOODS_RESOURCES = {
    "all_goods_of_age",
    "all_goods_of_next_age",
    "all_goods_of_previous_age",
    "random_good",
    "random_good_of_age",
    "random_good_of_next_age",
    "random_good_of_previous_age",
    "special_goods_up_to_age",
}

NON_GOODS_RESOURCE_TYPES = {
    "blueprint",
    "blueprints",
    "chest",
    "consumable",
    "forgepoint_package",
    "fragment",
    "genericreward",
    "set",
    "unit",
    "units",
}

SETTLEMENT_RESOURCES = {
    "aztecs",
    "colonists",
    "egyptians",
    "japanese",
    "mughals",
    "pirates",
    "polynesians",
    "vikings",
}

SINGLE_BUILDING_ATTRIBUTE_ALLOWLIST = {
    "generic_passive_bonus_maxvalue",
    "generic_production_bonus_maxvalue",
    BOOST_SPECIAL_GOODS_ATTR,
}

SKIP_GENERIC_KEYS = {
    "abilities",
    "asset_id",
    "available_products",
    "boosts",
    "components",
    "entity_levels",
    "environmentEffect",
    "flags",
    "id",
    "length",
    "lookup",
    "name",
    "placement",
    "production",
    "requirements",
    "resaleResources",
    "socialInteraction",
    "stateDefinitionHash",
    "staticResources",
    "tags",
    "type",
    "width",
}


def load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return raw["data"]
    if isinstance(raw, dict):
        return raw
    raise SystemExit("Unexpected JSON payload format")


def display_path(path: str) -> str:
    try:
        return os.path.relpath(os.path.abspath(path), BASE_DIR)
    except ValueError:
        return os.path.basename(path)


def safe_output_token(path: str) -> str:
    name = os.path.basename(path.rstrip(os.sep)) or "reference"
    if "." in name:
        name = os.path.splitext(name)[0]
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in name)


def excel_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def age_display_name(age: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", age)


def age_lookup_key(entity_id: str, era: str) -> str:
    return f"{entity_id}|{age_display_name(era)}"


def selected_age_display(era: str, all_ages: bool) -> str:
    return age_display_name(era) if all_ages else era


def as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def numeric_cell(value: Any) -> Any:
    if isinstance(value, float) and math.isclose(value, round(value)):
        return int(round(value))
    return value


def current_year_suffix() -> str:
    return datetime.now().strftime("%y")


def current_year_key() -> str:
    return datetime.now().strftime("%Y")


def event_reward_abbreviation(entity_id: str, year_suffix: Optional[str] = None) -> Optional[str]:
    if entity_id.startswith(GBG_REWARD_PREFIX):
        return None
    if entity_id.startswith(QI_REWARD_PREFIX):
        return None
    if entity_id.startswith(GE_REWARD_PREFIXES):
        return None
    suffix = year_suffix or current_year_suffix()
    match = re.match(rf"^{re.escape(MULTI_AGE_PREFIX)}([A-Za-z]+){re.escape(suffix)}[A-Za-z].*", entity_id)
    return match.group(1).upper() if match else None


def event_reward_abbreviations(records: Sequence[Dict[str, Any]]) -> List[str]:
    year_suffix = current_year_suffix()
    abbreviations = {
        abbreviation
        for record in records
        if (abbreviation := event_reward_abbreviation(str(record.get("entity_id", "")), year_suffix))
    }
    return sorted(abbreviations)


def event_reward_category_label(entity_id: str) -> Optional[str]:
    match = re.match(rf"^{re.escape(MULTI_AGE_PREFIX)}([A-Za-z]+)([0-9]{{2}})[A-Za-z].*", entity_id)
    if not match:
        return None
    abbreviation = match.group(1).upper()
    year = 2000 + int(match.group(2))
    return f"{abbreviation} {year} Event Rewards"


def building_category_label(entity_id: str) -> str:
    if entity_id.startswith(GBG_REWARD_PREFIX):
        return "GBG Rewards"
    if entity_id.startswith(QI_REWARD_PREFIX):
        return "QI Rewards"
    if entity_id.startswith(GE_REWARD_PREFIXES):
        return "GE Rewards"
    if event_label := event_reward_category_label(entity_id):
        return event_label
    return "Other Buildings"


def building_category_sort_key(label: str) -> Tuple[int, int, str]:
    priority = {
        ALL_BUILDING_CATEGORIES: 0,
        "QI Rewards": 1,
        "GBG Rewards": 2,
        "GE Rewards": 3,
        "Other Buildings": 99,
    }
    if event_match := re.match(r"^(.+) ([0-9]{4}) Event Rewards$", label):
        abbreviation, year = event_match.groups()
        return (10, -int(year), abbreviation)
    return (priority.get(label, 90), 0, label)


def building_category_options(records: Sequence[Dict[str, Any]]) -> List[str]:
    categories = {building_category_label(str(record.get("entity_id", ""))) for record in records}
    return [ALL_BUILDING_CATEGORIES, *sorted(categories, key=building_category_sort_key)]


def generated_event_color(index: int) -> str:
    hue = (0.12 + index * 0.61803398875) % 1.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.86, 0.55)
    return f"{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"


def load_event_color_registry(path: str = EVENT_COLOR_MAP_FILE) -> Dict[str, Dict[str, str]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    registry: Dict[str, Dict[str, str]] = {}
    for year, colors in payload.items():
        if not isinstance(year, str) or not isinstance(colors, dict):
            continue
        registry[year] = {
            str(abbreviation).upper(): str(color).upper()
            for abbreviation, color in colors.items()
            if re.fullmatch(r"[0-9A-Fa-f]{6}", str(color))
        }
    return registry


def save_event_color_registry(registry: Dict[str, Dict[str, str]], path: str = EVENT_COLOR_MAP_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)
        handle.write("\n")


def abbreviation_color_seed(abbreviation: str) -> int:
    digest = hashlib.sha1(abbreviation.upper().encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def next_unused_event_color(used_colors: set[str], event_index: int, abbreviation: str) -> str:
    start = abbreviation_color_seed(abbreviation) % len(EVENT_REWARD_COLORS)
    for offset in range(len(EVENT_REWARD_COLORS)):
        color = EVENT_REWARD_COLORS[(start + offset) % len(EVENT_REWARD_COLORS)]
        if color not in used_colors:
            return color
    attempt = event_index
    while True:
        color = generated_event_color(abbreviation_color_seed(abbreviation) + attempt)
        if color not in used_colors:
            return color
        attempt += 1


def event_color_map(event_abbreviations_: Sequence[str]) -> Dict[str, str]:
    abbreviations = sorted(dict.fromkeys(abbreviation.upper() for abbreviation in event_abbreviations_))
    registry = load_event_color_registry()
    year = current_year_key()
    year_colors = registry.setdefault(year, {})
    used_colors = set(REWARD_GROUP_COLORS.values())
    used_colors.update(color for color in year_colors.values() if color)

    changed = False
    for abbreviation in abbreviations:
        existing = year_colors.get(abbreviation)
        if existing and existing not in REWARD_GROUP_COLORS.values():
            continue
        if existing in REWARD_GROUP_COLORS.values():
            used_colors.discard(existing)
        color = next_unused_event_color(used_colors, len(year_colors), abbreviation)
        year_colors[abbreviation] = color
        used_colors.add(color)
        changed = True

    if changed:
        save_event_color_registry(registry)
    return {abbreviation: year_colors[abbreviation] for abbreviation in abbreviations}


def apply_building_name_color_rules(
    sheet: Any,
    data_start: int,
    data_end: int,
    entity_col: int,
    event_abbreviations_: Sequence[str],
) -> None:
    if data_end < data_start:
        return

    entity_letter = get_column_letter(entity_col)
    entity_cell = f"${entity_letter}{data_start}"
    name_range = f"A{data_start}:A{data_end}"

    rules = [
        (f'LEFT({entity_cell},{len(GBG_REWARD_PREFIX)})="{GBG_REWARD_PREFIX}"', REWARD_GROUP_COLORS["GBG"]),
        (f'LEFT({entity_cell},{len(QI_REWARD_PREFIX)})="{QI_REWARD_PREFIX}"', REWARD_GROUP_COLORS["QI"]),
        (
            "OR("
            + ",".join(
                f'LEFT({entity_cell},{len(prefix)})="{prefix}"'
                for prefix in GE_REWARD_PREFIXES
            )
            + ")",
            REWARD_GROUP_COLORS["GE"],
        ),
    ]

    excluded_prefix_checks = [
        f'LEFT({entity_cell},{len(GBG_REWARD_PREFIX)})<>"{GBG_REWARD_PREFIX}"',
        f'LEFT({entity_cell},{len(QI_REWARD_PREFIX)})<>"{QI_REWARD_PREFIX}"',
        *[
            f'LEFT({entity_cell},{len(prefix)})<>"{prefix}"'
            for prefix in GE_REWARD_PREFIXES
        ],
    ]
    for abbreviation, color in event_color_map(event_abbreviations_).items():
        prefix = f"{MULTI_AGE_PREFIX}{abbreviation}{current_year_suffix()}"
        formula = (
            "AND("
            + ",".join(
                [
                    *excluded_prefix_checks,
                    f'LEFT({entity_cell},{len(prefix)})="{prefix}"',
                ]
            )
            + ")"
        )
        rules.append((formula, color))

    for formula, color in rules:
        sheet.conditional_formatting.add(
            name_range,
            FormulaRule(formula=[formula], fill=PatternFill("solid", fgColor=color)),
        )


def format_amount(value: float) -> str:
    if math.isclose(value, round(value)):
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def format_probability(value: float) -> str:
    return f"{value * 100:.2f}".rstrip("0").rstrip(".") + "%"


def is_road_connection_attr_key(key: str) -> bool:
    return (
        key in {"street_connection_level", "generic_street_connection_requirement"}
        or "streetconnectionrequirement" in key
        or "street_connection_requirement" in key
    )


def attr_label(key: str) -> str:
    if key == "area":
        return "Footprint Area"
    if is_road_connection_attr_key(key):
        return REQUIRE_ROAD_HEADER
    boost_production_labels = {
        "boost_coin_production_all": "Boost: Coin production percentage",
        "boost_forge_points_production_all": "Boost: Forge points production percentage",
        "boost_goods_production_all": "Boost: Goods production percentage",
        "boost_guild_goods_production_all": "Boost: Guild goods production percentage",
        "boost_medal_production_all": "Boost: Medal production percentage",
        "boost_special_goods_production_all": "Boost: Special goods production percentage",
        "boost_supply_production_all": "Boost: Supply production percentage",
    }
    if key in boost_production_labels:
        return boost_production_labels[key]
    if key == "prod_unit_current_age":
        return "Production: Current Age Unit"
    if key == "prod_unit_next_age":
        return "Production: Next Age Unit"
    if key == "prod_unit_rogue":
        return "Production: Rogue"
    if key == "prod_resource_premium":
        return "Production: Diamonds/day"
    if key == "prod_resource_money":
        return "Production: Coins"
    if key == "generic_limited_config_expiretime":
        return "Limited Config Expire Time (days)"
    if key == "happiness":
        return "Gross Happiness"
    if key == NET_HAPPINESS_ATTR:
        return "Net Happiness"
    if key == "happiness_demanded":
        return "Happiness Demand"
    if key == "static_population":
        return "Population"
    text = key.replace("prod_resource_", "Production: ")
    text = text.replace("prod_", "Production: ")
    text = text.replace("boost_", "Boost: ")
    text = text.replace("cost_", "Cost: ")
    text = text.replace("static_", "Static: ")
    text = text.replace("generic_", "")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.title()
    text = re.sub(r"\bStrategy Points\b", "FPs", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGuild Raids\b", "QI", text, flags=re.IGNORECASE)
    if key.startswith("boost_"):
        text = re.sub(r"\bAttacker\b", "Red", text)
        text = re.sub(r"\bDefender\b", "Blue", text)
    return text


def overall_ranking_attr_label(key: str) -> str:
    if key == NET_HAPPINESS_ATTR:
        return "Net Happiness"
    if key == "prod_resource_money":
        return "Base Production: Coin"
    if key == "prod_resource_supplies":
        return "Base Production: Supplies"
    return attr_label(key)


def overall_ranking_display_attr_keys(attr_keys: Sequence[str]) -> List[str]:
    display_keys: List[str] = []
    for key in attr_keys:
        if key in {"happiness_demanded", NET_HAPPINESS_ATTR}:
            continue
        display_keys.append(key)
        if key == "happiness" and NET_HAPPINESS_ATTR in attr_keys:
            display_keys.append(NET_HAPPINESS_ATTR)
    return display_keys


def display_attr_value(record: Dict[str, Any], key: str) -> float:
    if key == NET_HAPPINESS_ATTR:
        attrs = record.get("attrs", {})
        if isinstance(attrs, dict):
            return float(
                attrs.get(
                    NET_HAPPINESS_ATTR,
                    float(attrs.get("happiness", 0.0)) + float(attrs.get("happiness_demanded", 0.0)),
                )
            )
        return 0.0
    return effective_attr_value(record, key)


def attr_description(key: str) -> str:
    if key == "area":
        return "Footprint in tiles; lower is usually better."
    if is_road_connection_attr_key(key):
        return "Road requirement flag. Buildings that require a road are treated as one extra tile in efficiency rankings."
    if key.startswith("boost_att_boost_") or key.startswith("boost_def_boost_"):
        stat = "attack" if key.startswith("boost_att_boost_") else "defense"
        army = "blue/defending army" if "_defender_" in key else "red/attacking army"
        if key.endswith("_battleground"):
            scope = "Guild Battlegrounds"
        elif key.endswith("_guild_expedition"):
            scope = "Guild Expedition"
        elif key.endswith("_guild_raids"):
            scope = "QI"
        else:
            scope = "all non-QI combat"
        return f"Percentage {stat} boost for the {army} in {scope}."
    production_boost_descriptions = {
        "boost_coin_production_all": "Percentage boost to coin production. Used with the Main Controls base coin estimate when calculating effective coin output.",
        BOOST_FP_ATTR: "Percentage boost to Forge Point production. Used with the Main Controls base FP estimate when calculating effective FP output.",
        BOOST_GOODS_ATTR: "Percentage boost to regular goods production. Applies only to regular goods, not special goods or guild goods.",
        BOOST_GUILD_GOODS_ATTR: "Percentage boost to guild goods production. Applies only to guild goods.",
        BOOST_MEDALS_ATTR: "Percentage boost to medal production. Used with the Main Controls base medal estimate when calculating effective medal output.",
        BOOST_SPECIAL_GOODS_ATTR: "Percentage boost to special goods production. Applies only to special goods.",
        "boost_supply_production_all": "Percentage boost to supply production. This is shown for reference and defaults to zero weight.",
    }
    if key in production_boost_descriptions:
        return production_boost_descriptions[key]
    qi_boost_descriptions = {
        "boost_guild_raids_action_points_capacity_all": "Additional QI action point capacity provided by the building.",
        "boost_guild_raids_action_points_collection_all": "Additional QI action points collected from the building.",
        "boost_guild_raids_coins_production_all": "Percentage boost to QI coin production.",
        "boost_guild_raids_coins_start_all": "Starting QI coins granted by the building.",
        "boost_guild_raids_goods_start_all": "Starting QI goods granted by the building.",
        "boost_guild_raids_supplies_production_all": "Percentage boost to QI supply production.",
        "boost_guild_raids_supplies_start_all": "Starting QI supplies granted by the building.",
        "boost_guild_raids_units_start_all": "Starting QI units granted by the building.",
    }
    if key in qi_boost_descriptions:
        return qi_boost_descriptions[key]
    production_descriptions = {
        PROD_FP_ATTR: "Daily-equivalent Forge Points from the building, including motivated production options where applicable.",
        PROD_GOODS_ATTR: "Daily-equivalent regular goods total. Includes named goods, random/all goods by age, special goods up to age, and era_goods; excludes guild goods.",
        PROD_GUILD_GOODS_ATTR: "Daily-equivalent guild goods produced for the guild treasury.",
        PROD_MEDALS_ATTR: "Daily-equivalent medals from the building.",
        "prod_resource_money": "Base daily-equivalent coin production from the building before percentage boosts.",
        "prod_resource_supplies": "Base daily-equivalent supply production from the building before percentage boosts.",
        "prod_resource_all_goods_of_age": "Daily-equivalent current-age regular goods bundle. Already rolls into Goods Total.",
        "prod_resource_all_goods_of_next_age": "Daily-equivalent next-age regular goods bundle. Already rolls into Goods Total.",
        "prod_resource_all_goods_of_previous_age": "Daily-equivalent previous-age regular goods bundle. Already rolls into Goods Total.",
        "prod_resource_special_goods_up_to_age": "Daily-equivalent special goods up to the selected age. Already rolls into Goods Total.",
        "prod_resource_blueprint": "Daily-equivalent blueprint reward count.",
        "prod_resource_premium": "Daily-equivalent diamonds from the building.",
        "prod_unit_current_age": "Current-age military units produced per day-equivalent collection.",
        "prod_unit_next_age": "Next-age military units produced per day-equivalent collection.",
        "prod_unit_rogue": "Rogue units produced per day-equivalent collection.",
    }
    if key in production_descriptions:
        return production_descriptions[key]
    generic_descriptions = {
        "generic_autopolivatepriority_priority": "Internal auto-polivate priority from the reference data. Hidden and defaults to zero weight.",
        "generic_limited_config_collectionamount": "Limited-building collection count from reference config. Hidden and defaults to zero weight.",
        "generic_limited_config_expiretime": "Limited-building expiration duration, converted from seconds to days. Hidden and defaults to zero weight.",
        "generic_multiplycollection_chance": "Chance for a multiply-collection effect from reference config. Hidden and defaults to zero weight.",
        "generic_multiplycollection_charges": "Number of charges for a multiply-collection effect. Hidden and defaults to zero weight.",
        "generic_multiplycollection_factor": "Multiplier applied by a multiply-collection effect. Hidden and defaults to zero weight.",
    }
    if key in generic_descriptions:
        return generic_descriptions[key]
    if key == "happiness":
        return "Gross happiness provided by the building."
    if key == NET_HAPPINESS_ATTR:
        return "Gross happiness minus happiness demand; this is the weighted happiness value."
    if key == "happiness_demanded":
        return "Happiness demanded by the building, stored as a negative value."
    if key == "static_population":
        return "Net population: provided population is positive; required population is negative."
    if key.startswith("prod_"):
        return "Daily-equivalent production value from the best matching reference production option."
    if key.startswith("boost_"):
        return "Reference boost value for the selected age."
    if key.startswith("cost_"):
        return "Build or option cost from requirements; lower is usually better."
    if key.startswith("static_"):
        return "Static resource or population value for the selected age."
    if key.startswith("happiness_"):
        return "Happiness component value for the selected age."
    if key.startswith("generic_"):
        return "Other numeric reference attribute not covered by the main extractors."
    return "Numeric reference attribute."


def direction_for_attr(key: str) -> str:
    lower_terms = ("area", "cost_", "construction_time", "demand", "required", "road_level")
    if key == "area" or any(term in key for term in lower_terms):
        return "Lower"
    return "Higher"


def default_weight_for_attr(key: str) -> float:
    if key == "area":
        return 0.0
    if key == "boost_guild_raids_action_points_capacity_all":
        return 0.0
    if key in {
        "boost_guild_raids_coins_start_all",
        "boost_guild_raids_goods_start_all",
        "boost_guild_raids_units_start_all",
    }:
        return 0.5
    if key == "prod_unit_rogue":
        return 0.5
    if key in {BOOST_FP_ATTR, BOOST_GOODS_ATTR, BOOST_SPECIAL_GOODS_ATTR, BOOST_GUILD_GOODS_ATTR, BOOST_MEDALS_ATTR}:
        return 0.0
    if key in {"street_connection_level", "generic_street_connection_requirement"}:
        return 0.5
    if key.startswith("cost_population"):
        return 0.5
    if key.startswith("cost_money") or key.startswith("cost_supplies"):
        return 0.2
    if key == PROD_FP_ATTR:
        return 5.0
    if "forge_points_production" in key:
        return 4.0
    if key in {
        PROD_GOODS_ATTR,
        "prod_resource_all_goods_of_age",
        "prod_resource_random_good",
        "prod_resource_special_goods_up_to_age",
    }:
        return 3.0
    if key == PROD_GUILD_GOODS_ATTR:
        return 0.0
    if "goods_production" in key:
        return 2.5
    if "att_boost" in key or "def_boost" in key or "att_def_boost" in key or "attacker" in key or "defender" in key:
        if "guild_raids" in key:
            return 2.0
        if "battleground" in key:
            return 2.5
        if "guild_expedition" in key:
            return 1.0
        return 3.0
    if "guild_raids_action_points" in key:
        return 2.5
    if key.startswith("prod_fragments"):
        return 2.0
    if key.startswith("prod_units"):
        return 1.0
    if key.startswith("prod_resource_medals"):
        return 0.5
    if key.startswith("prod_resource_clan_power"):
        return 0.75
    if key.startswith("static_population"):
        return 0.5
    if key == NET_HAPPINESS_ATTR:
        return 0.5
    if key in {"happiness", "happiness_demanded"}:
        return 0.0
    if key.startswith("static_happiness") or key.startswith("happiness_provided"):
        return 0.5
    if "ranking_points" in key:
        return 0.1
    return 0.0


def is_fighting_attr(key: str) -> bool:
    if key in {"prod_unit_current_age", "prod_unit_next_age", "prod_unit_rogue"}:
        return True
    return key.startswith("boost_") and ("att_boost" in key or "def_boost" in key)


def is_guild_expedition_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "guild_expedition" in key


def is_guild_battleground_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "battleground" in key


def is_red_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "attacker" in key


def is_blue_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "defender" in key


def is_qi_blue_fighting_attr(key: str) -> bool:
    label = attr_label(key)
    return label in {
        "Boost: Att Boost: Blue QI",
        "Boost: Def Boost: Blue QI",
    }


def is_qi_red_fighting_attr(key: str) -> bool:
    label = attr_label(key)
    return label in {
        "Boost: Att Boost: Red QI",
        "Boost: Def Boost: Red QI",
    }


def is_attack_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "att_boost" in key


def is_defense_fighting_attr(key: str) -> bool:
    return is_fighting_attr(key) and "def_boost" in key


def fighting_gbg_focus_multiplier(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    return max(0.0, min(1.0, (5.0 - focus) / 4.0))


def fighting_ge_focus_multiplier(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    return max(0.0, min(1.0, (focus - 1.0) / 4.0))


def overall_gbg_budget(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    default_budget = OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GBG_WEIGHT_GROUP]
    if focus <= 3.0:
        return default_budget + (3.0 - focus) / 2.0 * (
            OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET - default_budget
        )
    return default_budget * (5.0 - focus) / 2.0


def overall_ge_budget(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    default_budget = OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GE_WEIGHT_GROUP]
    if focus >= 3.0:
        return default_budget + (focus - 3.0) / 2.0 * (
            OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET - default_budget
        )
    return default_budget * (focus - 1.0) / 2.0


def overall_gbg_budget_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL}"
    gbg_default = cached_number(OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GBG_WEIGHT_GROUP])
    combined = cached_number(OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET)
    return (
        f"IF({focus_cell}<=3,{gbg_default}+(3-{focus_cell})/2*({combined}-{gbg_default}),"
        f"{gbg_default}*(5-{focus_cell})/2)"
    )


def overall_ge_budget_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL}"
    ge_default = cached_number(OVERALL_FIGHTING_SUBGROUP_BUDGETS[OVERALL_FIGHTING_GE_WEIGHT_GROUP])
    combined = cached_number(OVERALL_FIGHTING_GBG_GE_COMBINED_BUDGET)
    return (
        f"IF({focus_cell}>=3,{ge_default}+({focus_cell}-3)/2*({combined}-{ge_default}),"
        f"{ge_default}*({focus_cell}-1)/2)"
    )


def fighting_gbg_weight_multiplier(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    base_weight = default_weight_for_attr("boost_att_boost_attacker_battleground")
    if math.isclose(base_weight, 0.0):
        return 0.0
    return FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT * (5.0 - focus) / 4.0 / base_weight


def fighting_ge_weight_multiplier(focus: float = DEFAULT_FIGHTING_GBG_GE_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    base_weight = default_weight_for_attr("boost_att_boost_attacker_guild_expedition")
    if math.isclose(base_weight, 0.0):
        return 0.0
    return FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT * (focus - 1.0) / 4.0 / base_weight


def fighting_gbg_weight_multiplier_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL}"
    combined = cached_number(FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT)
    base = cached_number(default_weight_for_attr("boost_att_boost_attacker_battleground"))
    return f"{combined}*(5-{focus_cell})/4/{base}"


def fighting_ge_weight_multiplier_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL}"
    combined = cached_number(FIGHTING_GBG_GE_COMBINED_RAW_WEIGHT)
    base = cached_number(default_weight_for_attr("boost_att_boost_attacker_guild_expedition"))
    return f"{combined}*({focus_cell}-1)/4/{base}"


def fighting_red_focus_multiplier(focus: float = DEFAULT_FIGHTING_RED_BLUE_FOCUS) -> float:
    return max(0.0, min(1.0, (5.0 - focus) / 4.0))


def fighting_blue_focus_multiplier(focus: float = DEFAULT_FIGHTING_RED_BLUE_FOCUS) -> float:
    return max(0.0, min(1.0, (focus - 1.0) / 4.0))


def fighting_current_age_unit_focus_multiplier(focus: float = DEFAULT_FIGHTING_UNIT_AGE_FOCUS) -> float:
    return max(0.0, min(1.0, (5.0 - focus) / 4.0))


def fighting_next_age_unit_focus_multiplier(focus: float = DEFAULT_FIGHTING_UNIT_AGE_FOCUS) -> float:
    return max(0.0, min(1.0, (focus - 1.0) / 4.0))


def fighting_attack_focus_multiplier(focus: float = DEFAULT_FIGHTING_ATTACK_DEFENSE_FOCUS) -> float:
    return max(0.0, min(1.0, (5.0 - focus) / 4.0))


def fighting_defense_focus_multiplier(focus: float = DEFAULT_FIGHTING_ATTACK_DEFENSE_FOCUS) -> float:
    return max(0.0, min(1.0, (focus - 1.0) / 4.0))


def fighting_weight_for_attr(key: str) -> float:
    if key == "prod_unit_current_age":
        return (
            fighting_current_age_unit_focus_multiplier()
            * FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT
            * DEFAULT_FIGHTING_WEIGHT_SCALE
        )
    if key == "prod_unit_next_age":
        return (
            fighting_next_age_unit_focus_multiplier()
            * FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT
            * DEFAULT_FIGHTING_WEIGHT_SCALE
        )
    if key == "prod_unit_rogue":
        return 1.0 * DEFAULT_FIGHTING_WEIGHT_SCALE
    if not is_fighting_attr(key):
        return 0.0
    weight = default_weight_for_attr(key)
    if is_guild_battleground_fighting_attr(key):
        weight *= fighting_gbg_weight_multiplier()
    elif is_guild_expedition_fighting_attr(key):
        weight *= fighting_ge_weight_multiplier()
    if is_red_fighting_attr(key):
        weight *= fighting_red_focus_multiplier()
    elif is_blue_fighting_attr(key):
        weight *= fighting_blue_focus_multiplier()
    if is_attack_fighting_attr(key):
        weight *= fighting_attack_focus_multiplier()
    elif is_defense_fighting_attr(key):
        weight *= fighting_defense_focus_multiplier()
    return weight * DEFAULT_FIGHTING_WEIGHT_SCALE


def qi_role_overall_multiplier(key: str, role: str = "Blue") -> float:
    if is_qi_blue_fighting_attr(key):
        if role == "Blue":
            return 1.0
        if role == "Both":
            return 8.0 / 15.0
        return 0.0
    if is_qi_red_fighting_attr(key):
        if role == "Red":
            return 1.0
        if role == "Both":
            return 8.0 / 15.0
        return 0.0
    return 1.0


def overall_weight_group_for_attr(key: str) -> str:
    if key in {"prod_unit_current_age", "prod_unit_next_age", "prod_unit_rogue"}:
        return OVERALL_FIGHTING_UNITS_WEIGHT_GROUP
    if is_guild_battleground_fighting_attr(key):
        return OVERALL_FIGHTING_GBG_WEIGHT_GROUP
    if is_guild_expedition_fighting_attr(key):
        return OVERALL_FIGHTING_GE_WEIGHT_GROUP
    if "guild_raids" in key and is_fighting_attr(key):
        return OVERALL_FIGHTING_QI_WEIGHT_GROUP
    if is_fighting_attr(key):
        return OVERALL_FIGHTING_ALL_WEIGHT_GROUP
    return OVERALL_NON_FIGHTING_WEIGHT_GROUP


def overall_weight_budget_for_group(group: str) -> float:
    if group == OVERALL_FIGHTING_GBG_WEIGHT_GROUP:
        return overall_gbg_budget()
    if group == OVERALL_FIGHTING_GE_WEIGHT_GROUP:
        return overall_ge_budget()
    return OVERALL_FIGHTING_SUBGROUP_BUDGETS.get(group, OVERALL_NON_FIGHTING_WEIGHT_BUDGET)


def overall_weight_budget_cell_value(group: str) -> Any:
    if group == OVERALL_FIGHTING_GBG_WEIGHT_GROUP:
        return f"={overall_gbg_budget_formula()}"
    if group == OVERALL_FIGHTING_GE_WEIGHT_GROUP:
        return f"={overall_ge_budget_formula()}"
    return overall_weight_budget_for_group(group)


def production_fp_goods_combined_raw_weight() -> float:
    return default_weight_for_attr(PROD_FP_ATTR) + default_weight_for_attr(PROD_GOODS_ATTR)


def production_fp_raw_weight(focus: float = DEFAULT_PRODUCTION_FP_GOODS_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    combined = production_fp_goods_combined_raw_weight()
    if focus <= 3.0:
        return combined - (focus - 1.0) / 2.0 * (combined / 2.0)
    return combined / 2.0 * (5.0 - focus) / 2.0


def production_goods_raw_weight(focus: float = DEFAULT_PRODUCTION_FP_GOODS_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    combined = production_fp_goods_combined_raw_weight()
    if focus >= 3.0:
        return combined / 2.0 + (focus - 3.0) / 2.0 * (combined / 2.0)
    return combined / 2.0 * (focus - 1.0) / 2.0


def production_fp_raw_weight_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{PRODUCTION_FP_GOODS_FOCUS_CELL}"
    combined = cached_number(production_fp_goods_combined_raw_weight())
    half = cached_number(production_fp_goods_combined_raw_weight() / 2.0)
    return f"IF({focus_cell}<=3,{combined}-({focus_cell}-1)/2*{half},{half}*(5-{focus_cell})/2)"


def production_goods_raw_weight_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{PRODUCTION_FP_GOODS_FOCUS_CELL}"
    half = cached_number(production_fp_goods_combined_raw_weight() / 2.0)
    return f"IF({focus_cell}>=3,{half}+({focus_cell}-3)/2*{half},{half}*({focus_cell}-1)/2)"


def farming_fp_raw_weight(focus: float = DEFAULT_PRODUCTION_FP_GOODS_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    combined = FARMING_FP_GOODS_COMBINED_RAW_WEIGHT
    if focus <= 3.0:
        return combined - (focus - 1.0) / 2.0 * (combined / 2.0)
    return combined / 2.0 * (5.0 - focus) / 2.0


def farming_goods_raw_weight(focus: float = DEFAULT_PRODUCTION_FP_GOODS_FOCUS) -> float:
    focus = max(1.0, min(5.0, focus))
    combined = FARMING_FP_GOODS_COMBINED_RAW_WEIGHT
    if focus >= 3.0:
        return combined / 2.0 + (focus - 3.0) / 2.0 * (combined / 2.0)
    return combined / 2.0 * (focus - 1.0) / 2.0


def farming_fp_raw_weight_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{PRODUCTION_FP_GOODS_FOCUS_CELL}"
    combined = cached_number(FARMING_FP_GOODS_COMBINED_RAW_WEIGHT)
    half = cached_number(FARMING_FP_GOODS_COMBINED_RAW_WEIGHT / 2.0)
    return f"IF({focus_cell}<=3,{combined}-({focus_cell}-1)/2*{half},{half}*(5-{focus_cell})/2)"


def farming_goods_raw_weight_formula() -> str:
    focus_cell = f"{CONTROLS_SHEET_REF}!{PRODUCTION_FP_GOODS_FOCUS_CELL}"
    half = cached_number(FARMING_FP_GOODS_COMBINED_RAW_WEIGHT / 2.0)
    return f"IF({focus_cell}>=3,{half}+({focus_cell}-3)/2*{half},{half}*({focus_cell}-1)/2)"


def overall_raw_weight_for_attr(key: str) -> float:
    if key in OVERALL_GOODS_TOTAL_COMPONENT_ATTRS:
        return 0.0
    if key == PROD_FP_ATTR:
        weight = production_fp_raw_weight()
    elif key == PROD_GOODS_ATTR:
        weight = production_goods_raw_weight()
    elif key == "prod_unit_current_age":
        weight = default_weight_for_attr("prod_unit_rogue") * fighting_current_age_unit_focus_multiplier()
    elif key == "prod_unit_next_age":
        weight = default_weight_for_attr("prod_unit_rogue") * fighting_next_age_unit_focus_multiplier()
    elif key in OVERALL_QI_START_ATTRS:
        weight = OVERALL_QI_START_RAW_WEIGHT
    elif key == PROD_GUILD_GOODS_ATTR:
        weight = default_weight_for_attr(PROD_GOODS_ATTR) / 5.0
    else:
        weight = default_weight_for_attr(key)
    if math.isclose(weight, 0.0):
        return 0.0
    if is_guild_battleground_fighting_attr(key):
        weight *= fighting_gbg_focus_multiplier()
    elif is_guild_expedition_fighting_attr(key):
        weight *= fighting_ge_focus_multiplier()
    if is_red_fighting_attr(key):
        weight *= fighting_red_focus_multiplier()
    elif is_blue_fighting_attr(key):
        weight *= fighting_blue_focus_multiplier()
    if is_attack_fighting_attr(key):
        weight *= fighting_attack_focus_multiplier()
    elif is_defense_fighting_attr(key):
        weight *= fighting_defense_focus_multiplier()
    weight *= qi_role_overall_multiplier(key)
    return weight


def overall_weight_map(attr_keys: Sequence[str]) -> Dict[str, float]:
    raw_weights = {key: overall_raw_weight_for_attr(key) for key in attr_keys}
    groups = {overall_weight_group_for_attr(key) for key in attr_keys}
    totals = {
        group: sum(
            abs(weight)
            for key, weight in raw_weights.items()
            if overall_weight_group_for_attr(key) == group
        )
        for group in groups
    }
    out: Dict[str, float] = {}
    for key, raw_weight in raw_weights.items():
        group = overall_weight_group_for_attr(key)
        total = totals[group]
        if math.isclose(raw_weight, 0.0) or math.isclose(total, 0.0):
            out[key] = 0.0
        else:
            out[key] = raw_weight * overall_weight_budget_for_group(group) / total
    return out


def fighting_weight_cell_value(key: str) -> Any:
    if key == "prod_unit_current_age":
        return (
            f"=(5-{CONTROLS_SHEET_REF}!{FIGHTING_UNIT_AGE_FOCUS_CELL})/4"
            f"*{cached_number(FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT)}"
            f"*{cached_number(DEFAULT_FIGHTING_WEIGHT_SCALE)}"
        )
    if key == "prod_unit_next_age":
        return (
            f"=({CONTROLS_SHEET_REF}!{FIGHTING_UNIT_AGE_FOCUS_CELL}-1)/4"
            f"*{cached_number(FIGHTING_CURRENT_NEXT_UNIT_COMBINED_RAW_WEIGHT)}"
            f"*{cached_number(DEFAULT_FIGHTING_WEIGHT_SCALE)}"
        )
    if key == "prod_unit_rogue":
        return 1.0 * DEFAULT_FIGHTING_WEIGHT_SCALE
    if not is_fighting_attr(key):
        return 0.0
    terms = [cached_number(default_weight_for_attr(key))]
    if is_guild_battleground_fighting_attr(key):
        terms.append(fighting_gbg_weight_multiplier_formula())
    elif is_guild_expedition_fighting_attr(key):
        terms.append(fighting_ge_weight_multiplier_formula())
    if is_red_fighting_attr(key):
        terms.append(f"(5-{CONTROLS_SHEET_REF}!{FIGHTING_RED_BLUE_FOCUS_CELL})/4")
    elif is_blue_fighting_attr(key):
        terms.append(f"({CONTROLS_SHEET_REF}!{FIGHTING_RED_BLUE_FOCUS_CELL}-1)/4")
    if is_attack_fighting_attr(key):
        terms.append(f"(5-{CONTROLS_SHEET_REF}!{FIGHTING_ATTACK_DEFENSE_FOCUS_CELL})/4")
    elif is_defense_fighting_attr(key):
        terms.append(f"({CONTROLS_SHEET_REF}!{FIGHTING_ATTACK_DEFENSE_FOCUS_CELL}-1)/4")
    if len(terms) == 1:
        return fighting_weight_for_attr(key)
    terms.append(cached_number(DEFAULT_FIGHTING_WEIGHT_SCALE))
    return "=" + "*".join(terms)


def qi_role_overall_multiplier_formula(key: str) -> Optional[str]:
    if is_qi_blue_fighting_attr(key):
        return f'IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Blue",1,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",8/15,0))'
    if is_qi_red_fighting_attr(key):
        return f'IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Red",1,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",8/15,0))'
    return None


def overall_raw_weight_cell_value(key: str) -> Any:
    if key in OVERALL_GOODS_TOTAL_COMPONENT_ATTRS:
        return 0.0
    if key == PROD_FP_ATTR:
        return f"={production_fp_raw_weight_formula()}"
    if key == PROD_GOODS_ATTR:
        return f"={production_goods_raw_weight_formula()}"
    if key == "prod_unit_current_age":
        return f"={cached_number(default_weight_for_attr('prod_unit_rogue'))}*(5-{CONTROLS_SHEET_REF}!{FIGHTING_UNIT_AGE_FOCUS_CELL})/4"
    if key == "prod_unit_next_age":
        return f"={cached_number(default_weight_for_attr('prod_unit_rogue'))}*({CONTROLS_SHEET_REF}!{FIGHTING_UNIT_AGE_FOCUS_CELL}-1)/4"
    if key in OVERALL_QI_START_ATTRS:
        return OVERALL_QI_START_RAW_WEIGHT
    if key == PROD_GUILD_GOODS_ATTR:
        base_weight = default_weight_for_attr(PROD_GOODS_ATTR) / 5.0
    else:
        base_weight = default_weight_for_attr(key)
    if math.isclose(base_weight, 0.0):
        return 0.0
    terms = [cached_number(base_weight)]
    if is_guild_battleground_fighting_attr(key):
        terms.append(f"(5-{CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL})/4")
    elif is_guild_expedition_fighting_attr(key):
        terms.append(f"({CONTROLS_SHEET_REF}!{FIGHTING_GBG_GE_FOCUS_CELL}-1)/4")
    if is_red_fighting_attr(key):
        terms.append(f"(5-{CONTROLS_SHEET_REF}!{FIGHTING_RED_BLUE_FOCUS_CELL})/4")
    elif is_blue_fighting_attr(key):
        terms.append(f"({CONTROLS_SHEET_REF}!{FIGHTING_RED_BLUE_FOCUS_CELL}-1)/4")
    if is_attack_fighting_attr(key):
        terms.append(f"(5-{CONTROLS_SHEET_REF}!{FIGHTING_ATTACK_DEFENSE_FOCUS_CELL})/4")
    elif is_defense_fighting_attr(key):
        terms.append(f"({CONTROLS_SHEET_REF}!{FIGHTING_ATTACK_DEFENSE_FOCUS_CELL}-1)/4")
    qi_role_formula = qi_role_overall_multiplier_formula(key)
    if qi_role_formula:
        terms.append(qi_role_formula)
    if len(terms) == 1:
        return base_weight
    return "=" + "*".join(terms)


def overall_weight_cell_value(row_idx: int) -> str:
    raw_col = get_column_letter(OVERALL_RAW_WEIGHT_COLUMN)
    group_col = get_column_letter(OVERALL_WEIGHT_GROUP_COLUMN)
    budget_col = get_column_letter(OVERALL_WEIGHT_BUDGET_COLUMN)
    raw_cell = f"{raw_col}{row_idx}"
    group_cell = f"{group_col}{row_idx}"
    budget_cell = f"{budget_col}{row_idx}"
    return (
        f'=IF({raw_cell}=0,0,{raw_cell}*IFERROR({budget_cell}/'
        f'SUMIF(${group_col}:${group_col},{group_cell},${raw_col}:${raw_col}),0))'
    )


def formula_expr(value: Any) -> str:
    if isinstance(value, str) and value.startswith("="):
        return value[1:]
    numeric = as_float(value)
    return cached_number(numeric if numeric is not None else 0.0)


def weight_mode_formula(default_value: Any, override_col: int, row_idx: int) -> str:
    default_expr = formula_expr(default_value)
    override_cell = f"{get_column_letter(override_col)}{row_idx}"
    return (
        f'=IF({ADVANCED_WEIGHT_MODE_CELL}="Default",{default_expr},'
        f'IF(ISBLANK({override_cell}),{default_expr},{override_cell}))'
    )


def fp_goods_weight_for_attr(key: str) -> float:
    if key == PROD_FP_ATTR:
        return farming_fp_raw_weight()
    if key == PROD_GOODS_ATTR:
        return farming_goods_raw_weight()
    return FARMING_SECONDARY_RAW_WEIGHTS.get(key, 0.0)


def fp_goods_weight_cell_value(key: str) -> Any:
    if key == PROD_FP_ATTR:
        return f"={farming_fp_raw_weight_formula()}"
    if key == PROD_GOODS_ATTR:
        return f"={farming_goods_raw_weight_formula()}"
    return fp_goods_weight_for_attr(key)


def has_any_default_weight(key: str) -> bool:
    return any(
        not math.isclose(weight_func(key), 0.0)
        for weight_func in (
            default_weight_for_attr,
            overall_raw_weight_for_attr,
            fighting_weight_for_attr,
            fp_goods_weight_for_attr,
            qi_weight_for_attr,
        )
    )


def is_qi_attr(key: str) -> bool:
    label = attr_label(key)
    return "qi" in key or "guild_raids" in key or "QI" in label


def qi_weight_for_attr(key: str) -> float:
    if not is_qi_attr(key):
        return 0.0
    label = attr_label(key)
    if label in {
        "Boost: Att Boost: Blue QI",
    }:
        return 8.0
    if label in {
        "Boost: Def Boost: Blue QI",
    }:
        return 5.6
    if label in {
        "Boost: Att Boost: Red QI",
    }:
        return 8.0
    if label in {
        "Boost: Def Boost: Red QI",
    }:
        return 5.6
    if label == "Boost: QI Action Points Collection All":
        return 20.0
    if label == "Boost: QI Action Points Capacity All":
        return 1.0
    if label == "Boost: QI Coins Start All":
        return 3.0
    if label == "Boost: QI Goods Start All":
        return 5.0
    if label == "Boost: QI Units Start All":
        return 5.0
    default = default_weight_for_attr(key)
    return default if not math.isclose(default, 0.0) else 1.0


def qi_role_weight_formula(key: str) -> Optional[str]:
    label = attr_label(key)
    if label == "Boost: Att Boost: Blue QI":
        return f'=IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Blue",15,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",8,0))'
    if label == "Boost: Def Boost: Blue QI":
        return f'=IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Blue",10.5,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",5.6,0))'
    if label == "Boost: Att Boost: Red QI":
        return f'=IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Red",15,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",8,0))'
    if label == "Boost: Def Boost: Red QI":
        return f'=IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Red",10.5,IF({CONTROLS_SHEET_REF}!{QI_FIGHTER_ROLE_CELL}="Both",5.6,0))'
    return None


def should_include_attribute(key: str) -> bool:
    if key == "prod_resource_consumable":
        return False
    if key == "prod_resource_forgepoint_package":
        return False
    if key in {"prod_resource_unit", "prod_units"}:
        return False
    if key == "prod_resource_chest":
        return False
    if key == "generic_value_premiumequivalent":
        return False
    if key == "prod_resource_set":
        return False
    if key in {"generic_rankingpoints_specialfactor", "generic_rankingpoints_typefactor"}:
        return False
    if key == "prod_fragments":
        return False
    if key.startswith("prod_fragments_"):
        return False
    if key == "prod_kit_fragments":
        return False
    if key in {"generic_happiness_provided", "generic_happiness_demanded"}:
        return False
    if re.fullmatch(r"generic_strategy_points_for_upgrade_\d+", key):
        return False
    if key in {
        "generic_chain_config_restartsproductiononchainchange",
        "generic_construction_time",
        "generic_constructiontime_instantfinishcost_resources_guild_raids_currency",
        "generic_constructiontime_time",
        "generic_firstlevelforgepointupgradeamount",
        "generic_usable_slots",
    }:
        return False
    if key.startswith("generic_chain_linkpositions_"):
        return False
    if key.startswith("generic_chain_config_bonuses_") and key.endswith("_level"):
        return False
    if "buildresourcesrequirement" in key:
        return False
    for prefix in ("cost_", "prod_resource_", "static_"):
        if not key.startswith(prefix):
            continue
        resource = key.removeprefix(prefix)
        if resource in SETTLEMENT_RESOURCES:
            return False
    if key.startswith("cost_"):
        resource = key.removeprefix("cost_")
        if resource not in CORE_RESOURCES and resource != "goods_total":
            return False
    return True


def selected_components(entity: Dict[str, Any], era: str) -> List[Tuple[str, Dict[str, Any]]]:
    components = entity.get("components")
    if not isinstance(components, dict):
        return []
    out: List[Tuple[str, Dict[str, Any]]] = []
    for key in ("AllAge", era):
        component = components.get(key)
        if isinstance(component, dict):
            out.append((key, component))
    return out


def native_era(entity: Dict[str, Any]) -> Optional[str]:
    requirements = entity.get("requirements")
    if isinstance(requirements, dict) and isinstance(requirements.get("min_era"), str):
        min_era = requirements["min_era"]
        return min_era if min_era in AGE_ORDER else None
    entity_id = entity.get("id")
    if isinstance(entity_id, str):
        for era in AGE_ORDER:
            if f"_{era}_" in entity_id:
                return era
    return None


def is_available_for_age(entity: Dict[str, Any], era: str) -> bool:
    components = entity.get("components")
    if isinstance(components, dict) and (era in components or "AllAge" in components):
        return True
    min_era = native_era(entity)
    if min_era is None:
        return True
    return AGE_ORDER.get(min_era, 999) <= AGE_ORDER.get(era, 999)


def extract_size(entity: Dict[str, Any], era: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    for _component_key, component in reversed(selected_components(entity, era)):
        placement = component.get("placement")
        if not isinstance(placement, dict):
            continue
        size = placement.get("size")
        if not isinstance(size, dict):
            continue
        x = size.get("x")
        y = size.get("y")
        if isinstance(x, int) and isinstance(y, int):
            return y, x, x * y
    width = entity.get("width")
    length = entity.get("length")
    if isinstance(width, int) and isinstance(length, int):
        return width, length, width * length
    return None, None, None


def resource_key(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


def resource_attr_key(name: str) -> str:
    key = resource_key(name)
    return RESOURCE_ATTR_ALIASES.get(key, key)


def is_goods_resource_key(key: str) -> bool:
    if key in AGGREGATE_GOODS_RESOURCES:
        return True
    if key in CORE_RESOURCES or key in SETTLEMENT_RESOURCES or key in NON_GOODS_RESOURCE_TYPES:
        return False
    return True


def goods_resource_audit_rows(attr_keys: Sequence[str]) -> List[Tuple[str, str, str, str]]:
    discovered_sources: Dict[str, set[str]] = {}
    prefixes = (
        ("prod_resource_", "Production"),
        ("cost_", "Cost"),
        ("static_", "Static"),
    )
    for attr_key in attr_keys:
        for prefix, source in prefixes:
            if not attr_key.startswith(prefix):
                continue
            resource = attr_key.removeprefix(prefix)
            if resource == "goods_total" or not is_goods_resource_key(resource):
                continue
            discovered_sources.setdefault(resource, set()).add(source)

    resources = set(AGGREGATE_GOODS_RESOURCES)
    resources.update(discovered_sources)
    rows: List[Tuple[str, str, str, str]] = []
    for resource in sorted(resources):
        if resource in AGGREGATE_GOODS_RESOURCES:
            classification = "Configured aggregate goods key"
            note = "Always treated as goods by workbook configuration."
        else:
            classification = "Assumed goods by non-core rule"
            note = "Not listed as core, settlement, or excluded non-goods resource."
        rows.append(
            (
                resource,
                classification,
                ", ".join(sorted(discovered_sources.get(resource, ()))) or "Not discovered in this workbook",
                note,
            )
        )
    return rows


def add_attr(attrs: Dict[str, float], key: str, value: Any, factor: float = 1.0) -> None:
    numeric = as_float(value)
    if numeric is None:
        return
    attrs[key] = attrs.get(key, 0.0) + numeric * factor


def collect_resources(attrs: Dict[str, float], prefix: str, container: Any, factor: float = 1.0) -> None:
    if isinstance(container, dict):
        resources = container.get("resources")
        if isinstance(resources, dict):
            if any(isinstance(value, (dict, list)) for value in resources.values()):
                collect_resources(attrs, prefix, resources, factor)
                return
            for name, value in resources.items():
                key = resource_attr_key(str(name))
                add_attr(attrs, f"{prefix}_{key}", value, factor)
                if is_goods_resource_key(key):
                    add_attr(attrs, f"{prefix}_goods_total", value, factor)
        elif isinstance(resources, list):
            for item in resources:
                collect_resources(attrs, prefix, item, factor)
        elif container.get("type") and ("amount" in container or "value" in container):
            key = resource_attr_key(str(container.get("type")))
            amount = container.get("amount", container.get("value"))
            add_attr(attrs, f"{prefix}_{key}", amount, factor)
            if is_goods_resource_key(key):
                add_attr(attrs, f"{prefix}_goods_total", amount, factor)


def collect_guild_goods(attrs: Dict[str, float], container: Any, factor: float = 1.0) -> None:
    if isinstance(container, dict):
        resources = container.get("resources")
        if isinstance(resources, dict):
            for name, value in resources.items():
                key = resource_attr_key(str(name))
                if is_goods_resource_key(key):
                    add_attr(attrs, PROD_GUILD_GOODS_ATTR, value, factor)
        elif isinstance(resources, list):
            for item in resources:
                collect_guild_goods(attrs, item, factor)
        elif container.get("type") and ("amount" in container or "value" in container):
            key = resource_attr_key(str(container.get("type")))
            amount = container.get("amount", container.get("value"))
            if is_goods_resource_key(key):
                add_attr(attrs, PROD_GUILD_GOODS_ATTR, amount, factor)


def collect_costs(attrs: Dict[str, float], container: Any) -> None:
    if isinstance(container, dict):
        collect_resources(attrs, "cost", container)
        cost = container.get("cost")
        if isinstance(cost, dict):
            collect_resources(attrs, "cost", cost)


def collect_static_resources(attrs: Dict[str, float], entity: Dict[str, Any], era: str) -> None:
    for _component_key, component in selected_components(entity, era):
        collect_resources(attrs, "static", component.get("staticResources"))
    collect_resources(attrs, "static", entity.get("staticResources"))


def collect_happiness(attrs: Dict[str, float], entity: Dict[str, Any], era: str) -> None:
    def walk(obj: Any, path: Sequence[str]) -> None:
        numeric = as_float(obj)
        if numeric is not None:
            if path == ["provided"]:
                add_attr(attrs, "happiness", numeric)
                add_attr(attrs, NET_HAPPINESS_ATTR, numeric)
            elif path == ["demanded"]:
                add_attr(attrs, "happiness_demanded", -numeric)
                add_attr(attrs, NET_HAPPINESS_ATTR, -numeric)
            else:
                add_attr(attrs, "happiness_" + "_".join(path), numeric)
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                walk(value, [*path, resource_key(str(key))])
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                walk(value, [*path, str(idx + 1)])

    for _component_key, component in selected_components(entity, era):
        happiness = component.get("happiness")
        if isinstance(happiness, (dict, list)):
            walk(happiness, [])


def option_time_factor(option: Dict[str, Any]) -> float:
    for key in ("time", "production_time", "duration"):
        numeric = as_float(option.get(key))
        if numeric and numeric > 0:
            return 86400.0 / numeric
    return 1.0


def probability_factor(item: Dict[str, Any]) -> float:
    for key in ("dropChance", "drop_chance", "chance", "probability"):
        numeric = as_float(item.get(key))
        if numeric is None:
            continue
        return numeric / 100.0 if numeric > 1 else numeric
    return 1.0


def component_reward_lookup(component: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup = component.get("lookup")
    if not isinstance(lookup, dict):
        return {}
    rewards = lookup.get("rewards")
    if isinstance(rewards, dict):
        return {str(key): value for key, value in rewards.items() if isinstance(value, dict)}
    if isinstance(rewards, list):
        out: Dict[str, Dict[str, Any]] = {}
        for reward in rewards:
            if isinstance(reward, dict) and isinstance(reward.get("id"), str):
                out[reward["id"]] = reward
        return out
    return {}


def unit_attribute_key(reward: Dict[str, Any]) -> str:
    unit_type = resource_key(str(reward.get("unitTypeId", reward.get("subType", ""))))
    reward_id = str(reward.get("id", "")).casefold()
    name = str(reward.get("name", "")).casefold()
    if unit_type == "rogue" or "rogue" in reward_id or "rogue" in name:
        return "prod_unit_rogue"
    if "#nextera#" in reward_id or "next age" in name:
        return "prod_unit_next_age"
    return "prod_unit_current_age"


def add_unit_production(attrs: Dict[str, float], reward: Dict[str, Any], factor: float) -> None:
    amount = as_float(reward.get("amount", reward.get("value", 1))) or 1.0
    add_attr(attrs, unit_attribute_key(reward), amount, factor)


def forgepoint_package_value(reward: Dict[str, Any]) -> float:
    reward_type = resource_key(str(reward.get("type", "")))
    if reward_type == "forgepoint_package":
        package_value = as_float(reward.get("subType")) or 0.0
        amount = as_float(reward.get("amount", reward.get("value", 1))) or 1.0
        return package_value * amount
    if reward_type == "set":
        rewards = reward.get("rewards")
        if isinstance(rewards, list):
            return sum(forgepoint_package_value(item) for item in rewards if isinstance(item, dict))
    return 0.0


def forgepoint_package_display_name(reward: Dict[str, Any]) -> str:
    name = reward.get("name") or reward.get("id")
    return str(name) if name else "Forge Point Package"


def kit_fragment_key(reward: Dict[str, Any]) -> Optional[str]:
    if resource_key(str(reward.get("subType", reward.get("type", "")))) != "fragment":
        return None
    assembled = reward.get("assembledReward")
    if isinstance(assembled, dict):
        name = assembled.get("name") or assembled.get("id")
        assembled_text = " ".join(
            str(assembled.get(key, "")) for key in ("subType", "id", "name", "description")
        ).casefold()
        if "kit" not in assembled_text:
            return None
        if isinstance(name, str) and name:
            return "prod_fragments_" + resource_key(name)
    reward_id = reward.get("id")
    reward_text = " ".join(str(reward.get(key, "")) for key in ("id", "name", "description")).casefold()
    if isinstance(reward_id, str) and reward_id.startswith("fragment#") and "kit" in reward_text:
        parts = reward_id.split("#")
        if len(parts) >= 2:
            return "prod_fragments_" + resource_key(parts[1])
    return None


def collect_reward(
    attrs: Dict[str, float],
    reward: Dict[str, Any],
    factor: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    reward = resolved_reward(reward, reward_lookup)
    reward_type = resource_key(str(reward.get("type", "")))
    if reward_type == "chest":
        possible_rewards = reward.get("possible_rewards") or reward.get("possibleRewards")
        if isinstance(possible_rewards, list):
            for item in possible_rewards:
                if not isinstance(item, dict):
                    continue
                nested_reward = item.get("reward")
                if isinstance(nested_reward, dict):
                    collect_reward(attrs, nested_reward, factor * probability_factor(item), reward_lookup)
        return
    if reward_type == "unit":
        add_unit_production(attrs, reward, factor)
        return
    package_fps = forgepoint_package_value(reward)
    if package_fps:
        add_attr(attrs, "prod_resource_strategy_points", package_fps, factor)
        return
    if reward_type == "resource":
        subtype = resource_attr_key(str(reward.get("subType", "")))
        amount = reward.get("amount", reward.get("value"))
        if subtype and amount is not None:
            add_attr(attrs, f"prod_resource_{subtype}", amount, factor)
            if is_goods_resource_key(subtype):
                add_attr(attrs, PROD_GOODS_ATTR, amount, factor)
        return

    collect_resources(attrs, "prod_resource", reward, factor)
    subtype = resource_key(str(reward.get("subType", reward.get("type", ""))))
    amount = reward.get("amount", reward.get("value", 1))
    if subtype == "fragment":
        add_attr(attrs, "prod_fragments", amount, factor)
        fragment_key = kit_fragment_key(reward)
        if fragment_key:
            add_attr(attrs, "prod_kit_fragments", amount, factor)
            add_attr(attrs, fragment_key, amount, factor)
    elif subtype in {"unit", "units"}:
        add_unit_production(attrs, reward, factor)
    elif subtype in {"blueprint", "blueprints"}:
        add_attr(attrs, "prod_blueprints", amount, factor)


def collect_product(
    attrs: Dict[str, float],
    product: Any,
    factor: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    if resource_key(str(product.get("type", ""))) == "unit":
        add_unit_production(attrs, product, factor)
        return

    collect_resources(attrs, "prod_resource", product, factor)
    player_resources = product.get("playerResources")
    if isinstance(player_resources, dict):
        collect_resources(attrs, "prod_resource", player_resources, factor)
    guild_resources = product.get("guildResources")
    if isinstance(guild_resources, dict):
        collect_guild_goods(attrs, guild_resources, factor)

    reward = product.get("reward")
    if isinstance(reward, dict):
        collect_reward(attrs, reward, factor, reward_lookup)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_product(attrs, nested, factor, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_factor = factor * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_product(attrs, nested, nested_factor, reward_lookup)


def resolved_reward(
    reward: Dict[str, Any],
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if reward_lookup and isinstance(reward.get("id"), str) and reward["id"] in reward_lookup:
        return {**reward_lookup[reward["id"]], **reward}
    return reward


def fragment_display_name(reward: Dict[str, Any]) -> str:
    assembled = reward.get("assembledReward")
    if isinstance(assembled, dict):
        name = assembled.get("name") or assembled.get("id")
        if isinstance(name, str) and name:
            return name
    name = reward.get("name") or reward.get("id")
    return str(name) if name else "Unnamed Fragment"


def fragment_amount_label(amount: float, time_factor: float, probability: float) -> str:
    daily_amount = amount * time_factor * probability
    if not math.isclose(probability, 1.0):
        possible_daily = amount * time_factor
        return (
            f"{format_amount(daily_amount)}/day expected "
            f"({format_amount(possible_daily)}/day at {format_probability(probability)})"
        )
    return f"{format_amount(daily_amount)}/day"


def fp_amount_label(amount: float, time_factor: float, probability: float) -> str:
    daily_amount = amount * time_factor * probability
    if not math.isclose(probability, 1.0):
        possible_daily = amount * time_factor
        return (
            f"{format_amount(daily_amount)} FPs/day expected "
            f"({format_amount(possible_daily)} FPs/day at {format_probability(probability)})"
        )
    return f"{format_amount(daily_amount)} FPs/day"


def fp_named_amount_label(daily: float, possible: float, probability: float) -> str:
    if not math.isclose(probability, 1.0) and not math.isclose(daily, possible):
        return (
            f"{format_amount(daily)} FPs/day expected "
            f"({format_amount(possible)} FPs/day at {format_probability(probability)})"
        )
    return f"{format_amount(daily)} FPs/day"


def add_named_amount(
    values: Dict[str, Tuple[float, float, float]],
    label: str,
    amount: float,
    time_factor: float,
    probability: float,
) -> None:
    daily = amount * time_factor * probability
    possible = amount * time_factor
    if label in values:
        old_daily, old_possible, old_probability = values[label]
        values[label] = (old_daily + daily, old_possible + possible, min(old_probability, probability))
    else:
        values[label] = (daily, possible, probability)


def named_amount_label(daily: float, possible: float, probability: float) -> str:
    if not math.isclose(probability, 1.0) and not math.isclose(daily, possible):
        return (
            f"{format_amount(daily)}/day expected "
            f"({format_amount(possible)}/day at {format_probability(probability)})"
        )
    return f"{format_amount(daily)}/day"


def collect_fragment_product(
    fragments: Dict[str, Tuple[float, float, float]],
    product: Any,
    time_factor: float,
    probability: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    reward = product.get("reward")
    if isinstance(reward, dict):
        resolved = resolved_reward(reward, reward_lookup)
        subtype = resource_key(str(resolved.get("subType", resolved.get("type", ""))))
        if subtype == "fragment":
            amount = as_float(resolved.get("amount", resolved.get("value", 1))) or 1.0
            label = fragment_display_name(resolved)
            add_named_amount(fragments, label, amount, time_factor, probability)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_fragment_product(fragments, nested, time_factor, probability, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_probability = probability * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_fragment_product(fragments, nested, time_factor, nested_probability, reward_lookup)


def extract_fragment_production(entity: Dict[str, Any], era: str) -> str:
    fragments: Dict[str, Tuple[float, float, float]] = {}

    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))

    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            time_factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_fragment_product(fragments, item, time_factor, 1.0, reward_lookup)
                elif isinstance(value, dict):
                    collect_fragment_product(fragments, value, time_factor, 1.0, reward_lookup)

    return "; ".join(
        f"{name}: {named_amount_label(daily, possible, probability)}"
        for name, (daily, possible, probability) in sorted(fragments.items())
    )


def reward_set_display_name(reward: Dict[str, Any]) -> Optional[str]:
    if forgepoint_package_value(reward):
        return None
    if resource_key(str(reward.get("type", ""))) != "set":
        return None
    name = reward.get("name") or reward.get("id")
    return str(name) if name else "Unnamed Reward Set"


def collect_reward_set_product(
    reward_sets: Dict[str, Tuple[float, float, float]],
    product: Any,
    time_factor: float,
    probability: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    reward = product.get("reward")
    if isinstance(reward, dict):
        resolved = resolved_reward(reward, reward_lookup)
        name = reward_set_display_name(resolved)
        if name:
            amount = as_float(resolved.get("amount", resolved.get("value", 1))) or 1.0
            total_amount = as_float(resolved.get("totalAmount"))
            if total_amount is not None:
                amount *= total_amount
            add_named_amount(reward_sets, name, amount, time_factor, probability)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_reward_set_product(reward_sets, nested, time_factor, probability, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_probability = probability * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_reward_set_product(reward_sets, nested, time_factor, nested_probability, reward_lookup)


def extract_reward_set_production(entity: Dict[str, Any], era: str) -> str:
    reward_sets: Dict[str, Tuple[float, float, float]] = {}

    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))

    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            time_factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_reward_set_product(reward_sets, item, time_factor, 1.0, reward_lookup)
                elif isinstance(value, dict):
                    collect_reward_set_product(reward_sets, value, time_factor, 1.0, reward_lookup)

    return "; ".join(
        f"{name}: {named_amount_label(daily, possible, probability)}"
        for name, (daily, possible, probability) in sorted(reward_sets.items())
    )


def collect_consumable_product(
    consumables: Dict[str, Tuple[float, float, float]],
    product: Any,
    time_factor: float,
    probability: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    reward = product.get("reward")
    if isinstance(reward, dict):
        resolved = resolved_reward(reward, reward_lookup)
        reward_type = resource_key(str(resolved.get("type", "")))
        subtype = resource_key(str(resolved.get("subType", "")))
        if reward_type == "consumable" and subtype != "fragment":
            name = resolved.get("name") or resolved.get("id") or "Consumable"
            amount = as_float(resolved.get("amount", resolved.get("value", 1))) or 1.0
            add_named_amount(consumables, str(name), amount, time_factor, probability)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_consumable_product(consumables, nested, time_factor, probability, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_probability = probability * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_consumable_product(consumables, nested, time_factor, nested_probability, reward_lookup)


def extract_consumable_production(entity: Dict[str, Any], era: str) -> str:
    consumables: Dict[str, Tuple[float, float, float]] = {}

    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))

    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            time_factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_consumable_product(consumables, item, time_factor, 1.0, reward_lookup)
                elif isinstance(value, dict):
                    collect_consumable_product(consumables, value, time_factor, 1.0, reward_lookup)

    return "; ".join(
        f"{name}: {named_amount_label(daily, possible, probability)}"
        for name, (daily, possible, probability) in sorted(consumables.items())
    )


def collect_fp_package_product(
    packages: Dict[str, Tuple[float, float, float]],
    product: Any,
    time_factor: float,
    probability: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    reward = product.get("reward")
    if isinstance(reward, dict):
        resolved = resolved_reward(reward, reward_lookup)
        package_fps = forgepoint_package_value(resolved)
        if package_fps:
            add_named_amount(packages, forgepoint_package_display_name(resolved), package_fps, time_factor, probability)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_fp_package_product(packages, nested, time_factor, probability, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_probability = probability * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_fp_package_product(packages, nested, time_factor, nested_probability, reward_lookup)


def extract_fp_package_production(entity: Dict[str, Any], era: str) -> str:
    packages: Dict[str, Tuple[float, float, float]] = {}

    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))

    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            time_factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_fp_package_product(packages, item, time_factor, 1.0, reward_lookup)
                elif isinstance(value, dict):
                    collect_fp_package_product(packages, value, time_factor, 1.0, reward_lookup)

    return "; ".join(
        f"{name}: {fp_named_amount_label(daily, possible, probability)}"
        for name, (daily, possible, probability) in sorted(packages.items())
    )


def chest_detail_label(chest_name: str, reward: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    reward_type = resource_key(str(reward.get("type", "")))
    subtype = resource_key(str(reward.get("subType", "")))
    amount = as_float(reward.get("amount", reward.get("value", 1))) or 1.0

    if reward_type == "unit":
        name = reward.get("name") or reward.get("id") or "Unnamed Unit"
        return f"Unit: {name}", amount
    if reward_type == "blueprint":
        name = reward.get("name") or chest_name or reward.get("id") or "Blueprint"
        return f"Blueprint: {chest_name} - {name}" if chest_name and chest_name != name else f"Blueprint: {name}", amount
    if subtype == "fragment":
        return f"Fragment: {fragment_display_name(reward)}", amount
    return None


def chest_aggregate_amount_label(amount: float, time_factor: float, probability: float) -> str:
    daily_amount = amount * time_factor * probability
    if not math.isclose(probability, 1.0):
        possible_daily = amount * time_factor
        return (
            f"{format_amount(daily_amount)}/day expected "
            f"({format_amount(possible_daily)}/day at {format_probability(probability)})"
        )
    return f"{format_amount(daily_amount)}/day"


def collect_chest_product(
    chest_details: Dict[str, Tuple[float, float, float]],
    product: Any,
    time_factor: float,
    probability: float,
    reward_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not isinstance(product, dict):
        return

    reward = product.get("reward")
    if isinstance(reward, dict):
        resolved = resolved_reward(reward, reward_lookup)
        if resource_key(str(resolved.get("type", ""))) == "chest":
            chest_name = str(resolved.get("name") or resolved.get("id") or "Chest")
            possible_rewards = resolved.get("possible_rewards") or resolved.get("possibleRewards")
            if isinstance(possible_rewards, list):
                blueprint_total = 0.0
                for item in possible_rewards:
                    if not isinstance(item, dict):
                        continue
                    nested_reward = item.get("reward")
                    if not isinstance(nested_reward, dict):
                        continue
                    nested_probability = probability * probability_factor(item)
                    if resource_key(str(nested_reward.get("type", ""))) == "blueprint":
                        blueprint_total += (
                            (as_float(nested_reward.get("amount", nested_reward.get("value", 1))) or 1.0)
                            * probability_factor(item)
                        )
                        continue
                    detail = chest_detail_label(chest_name, nested_reward)
                    if detail is None:
                        continue
                    label, amount = detail
                    add_named_amount(chest_details, label, amount, time_factor, nested_probability)
                if blueprint_total:
                    add_named_amount(chest_details, f"Blueprint: {chest_name}", blueprint_total, time_factor, probability)

    for key in ("product", "assembledReward"):
        nested = product.get(key)
        if isinstance(nested, dict):
            collect_chest_product(chest_details, nested, time_factor, probability, reward_lookup)

    for key in ("products", "possible_rewards", "possibleRewards"):
        values = product.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            nested_probability = probability * probability_factor(item)
            nested = item.get("product") or item.get("reward") or item
            collect_chest_product(chest_details, nested, time_factor, nested_probability, reward_lookup)


def extract_chest_production(entity: Dict[str, Any], era: str) -> str:
    chest_details: Dict[str, Tuple[float, float, float]] = {}

    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))

    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            time_factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_chest_product(chest_details, item, time_factor, 1.0, reward_lookup)
                elif isinstance(value, dict):
                    collect_chest_product(chest_details, value, time_factor, 1.0, reward_lookup)

    return "; ".join(
        f"{name}: {named_amount_label(daily, possible, probability)}"
        for name, (daily, possible, probability) in sorted(chest_details.items())
    )


def merge_best(target: Dict[str, float], candidate: Dict[str, float]) -> None:
    for key, value in candidate.items():
        if key not in target or value > target[key]:
            target[key] = value


def single_product_resource(option: Dict[str, Any]) -> Optional[str]:
    product = option.get("product")
    if not isinstance(product, dict):
        return None
    resources = product.get("resources")
    if not isinstance(resources, dict) or len(resources) != 1:
        return None
    return resource_key(next(iter(resources)))


def is_regular_timed_factory(entity: Dict[str, Any]) -> bool:
    available_products = entity.get("available_products")
    if not isinstance(available_products, list) or len(available_products) < 4:
        return False

    resources: List[str] = []
    for option in available_products:
        if not isinstance(option, dict) or as_float(option.get("production_time")) is None:
            return False
        resource = single_product_resource(option)
        if resource is None:
            return False
        resources.append(resource)

    if len(set(resources)) != 1:
        return False

    entity_type = entity.get("type")
    resource = resources[0]
    if entity_type == "production" and len(available_products) == 6 and resource == "supplies":
        return True
    if entity_type == "goods" and resource not in CORE_RESOURCES:
        return True
    return False


def collect_production(attrs: Dict[str, float], entity: Dict[str, Any], era: str) -> None:
    production_sets: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    chain_products: List[Tuple[Any, Dict[str, Dict[str, Any]]]] = []
    for _component_key, component in selected_components(entity, era):
        production = component.get("production")
        if isinstance(production, dict):
            production_sets.append((production.get("options", []), component_reward_lookup(component)))
        chain = component.get("chain")
        if isinstance(chain, dict):
            config = chain.get("config")
            bonuses = config.get("bonuses") if isinstance(config, dict) else None
            if isinstance(bonuses, list):
                reward_lookup = component_reward_lookup(component)
                for bonus in bonuses:
                    if isinstance(bonus, dict):
                        chain_products.append((bonus.get("productions", []), reward_lookup))
    available_products = entity.get("available_products")
    if isinstance(available_products, list) and not is_regular_timed_factory(entity):
        production_sets.append((available_products, {}))

    best: Dict[str, float] = {}
    for options, reward_lookup in production_sets:
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            option_attrs: Dict[str, float] = {}
            factor = option_time_factor(option)
            for key in ("product", "products", "reward"):
                value = option.get(key)
                if isinstance(value, list):
                    for item in value:
                        collect_product(option_attrs, item, factor, reward_lookup)
                elif isinstance(value, dict):
                    collect_product(option_attrs, value, factor, reward_lookup)
            merge_best(best, option_attrs)

    for key, value in best.items():
        add_attr(attrs, key, value)

    for products, reward_lookup in chain_products:
        if not isinstance(products, list):
            continue
        for product in products:
            collect_product(attrs, product, 1.0, reward_lookup)


def add_boost_attr(attrs: Dict[str, float], boost: Dict[str, Any]) -> None:
    boost_type = resource_key(str(boost.get("type", "unknown")))
    target = resource_key(str(boost.get("targetedFeature", boost.get("target", "all"))))
    value = boost.get("value", boost.get("amount"))

    def add_boost_value(target_boost_type: str) -> None:
        if target_boost_type.endswith("_attacker_defender"):
            base_type = target_boost_type.removesuffix("_attacker_defender")
            add_attr(attrs, f"boost_{base_type}_attacker_{target}", value)
            add_attr(attrs, f"boost_{base_type}_defender_{target}", value)
            return
        add_attr(attrs, f"boost_{target_boost_type}_{target}", value)

    if boost_type.startswith("att_def_boost"):
        suffix = boost_type.removeprefix("att_def_boost")
        add_boost_value(f"att_boost{suffix}")
        add_boost_value(f"def_boost{suffix}")
        return
    add_boost_value(boost_type)


def collect_boosts(attrs: Dict[str, float], entity: Dict[str, Any], era: str) -> None:
    for _component_key, component in selected_components(entity, era):
        boost_container = component.get("boosts")
        if isinstance(boost_container, dict):
            boosts = boost_container.get("boosts")
        else:
            boosts = boost_container
        if not isinstance(boosts, list):
            continue
        for boost in boosts:
            if not isinstance(boost, dict):
                continue
            add_boost_attr(attrs, boost)
        chain = component.get("chain")
        if not isinstance(chain, dict):
            continue
        config = chain.get("config")
        bonuses = config.get("bonuses") if isinstance(config, dict) else None
        if not isinstance(bonuses, list):
            continue
        for bonus in bonuses:
            if not isinstance(bonus, dict):
                continue
            chain_boosts = bonus.get("boosts")
            if not isinstance(chain_boosts, list):
                continue
            for boost in chain_boosts:
                if not isinstance(boost, dict):
                    continue
                add_boost_attr(attrs, boost)


def collect_generic_numbers(attrs: Dict[str, float], entity: Dict[str, Any], era: str) -> None:
    def walk(obj: Any, path: Sequence[str], depth: int = 0) -> None:
        if depth > 4:
            return
        numeric = as_float(obj)
        if numeric is not None:
            attr_key = "generic_" + "_".join(path)
            if attr_key == "generic_limited_config_expiretime":
                numeric /= 86400.0
            add_attr(attrs, attr_key, numeric)
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in SKIP_GENERIC_KEYS:
                    continue
                walk(value, [*path, resource_key(str(key))], depth + 1)
        elif isinstance(obj, list):
            for idx, value in enumerate(obj[:10]):
                walk(value, [*path, str(idx + 1)], depth + 1)

    for key, value in entity.items():
        if key not in SKIP_GENERIC_KEYS:
            walk(value, [resource_key(str(key))])
    for _component_key, component in selected_components(entity, era):
        for key, value in component.items():
            if key not in SKIP_GENERIC_KEYS:
                walk(value, [resource_key(str(key))])


def format_environment_effect(effect: Dict[str, Any]) -> str:
    trigger = effect.get("trigger")
    effect_type = effect.get("type")
    name = effect.get("name")
    amount = effect.get("amount")

    parts: List[str] = []
    if trigger:
        parts.append(str(trigger))
    if effect_type:
        parts.append(str(effect_type))
    if name:
        parts.append(str(name))
    if amount not in (None, ""):
        parts.append(f"x{amount}")
    return ": ".join(parts[:1]) + (" - " + " ".join(parts[1:]) if len(parts) > 1 else "") if parts else ""


def extract_environment_effect(entity: Dict[str, Any], era: str) -> str:
    labels: List[str] = []
    for _component_key, component in selected_components(entity, era):
        environment_effect = component.get("environmentEffect")
        if not isinstance(environment_effect, dict):
            continue
        effects = environment_effect.get("effects")
        if not isinstance(effects, list):
            continue
        for effect in effects:
            if isinstance(effect, dict):
                label = format_environment_effect(effect)
                if label:
                    labels.append(label)
    return "; ".join(dict.fromkeys(labels))


def extract_attributes(entity: Dict[str, Any], era: str, area: Optional[int]) -> Dict[str, float]:
    attrs: Dict[str, float] = {}

    requirements = entity.get("requirements")
    if isinstance(requirements, dict):
        collect_costs(attrs, requirements)
        add_attr(attrs, "street_connection_level", requirements.get("street_connection_level"))

    collect_static_resources(attrs, entity, era)
    collect_happiness(attrs, entity, era)
    collect_production(attrs, entity, era)
    collect_boosts(attrs, entity, era)
    collect_generic_numbers(attrs, entity, era)
    return attrs


LEVEL_PATTERNS = (
    re.compile(r"^\s*(?:lv\.?|level)\s*(\d+)\s*[-:]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s*[-:]\s*(?:lv\.?|level)\s*(\d+)\s*$", re.IGNORECASE),
)


def leveled_building_key(name: str) -> Optional[Tuple[str, int]]:
    for pattern in LEVEL_PATTERNS:
        match = pattern.match(name)
        if not match:
            continue
        if match.re.pattern.startswith("^\\s*"):
            level = int(match.group(1))
            base_name = match.group(2)
        else:
            base_name = match.group(1)
            level = int(match.group(2))
        key = re.sub(r"\s+", " ", base_name).strip().casefold()
        return key, level
    return None


def highest_level_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_key: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []

    for record in records:
        level_info = leveled_building_key(str(record["name"]))
        if level_info is None:
            out.append(record)
            continue

        key, level = level_info
        existing = best_by_key.get(key)
        if existing is None or level > int(existing["_parsed_level"]):
            record["_parsed_level"] = level
            best_by_key[key] = record

    out.extend(best_by_key.values())
    out.sort(key=lambda record: str(record["name"]))
    for record in out:
        record.pop("_parsed_level", None)
    return out


def collect_records(entities: Dict[str, Any], era: str, available_only: bool) -> Tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []

    for entity_id, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        if not str(entity_id).startswith(("X_", "W_")):
            continue
        if str(entity_id).startswith("W_GuildRaids"):
            continue
        if entity.get("type") == "greatbuilding":
            continue
        available = is_available_for_age(entity, era)
        if available_only and not available:
            continue
        width, length, area = extract_size(entity, era)
        attrs = extract_attributes(entity, era, area)
        if (
            math.isclose(float(attrs.get("generic_rankingpoints_specialfactor", 0.0)), 0.0)
            and math.isclose(float(attrs.get("generic_rankingpoints_typefactor", 0.0)), 0.0)
        ):
            continue
        min_era = native_era(entity) or ""
        if min_era:
            continue
        attrs = {key: value for key, value in attrs.items() if should_include_attribute(key)}
        size = f"{width}x{length}" if width and length else ""
        records.append(
            {
                "entity_id": entity_id,
                "name": entity.get("name", entity_id),
                "type": entity.get("type", ""),
                "selected_age": era,
                "available": "Yes" if available else "No",
                "size": size,
                "area": area,
                "environment_effect": extract_environment_effect(entity, era),
                "fragment_production": extract_fragment_production(entity, era),
                "reward_production": "; ".join(
                    part
                    for part in (
                        extract_fragment_production(entity, era),
                        extract_reward_set_production(entity, era),
                        extract_consumable_production(entity, era),
                        extract_fp_package_production(entity, era),
                        extract_chest_production(entity, era),
                    )
                    if part
                ),
                "attrs": attrs,
            }
        )

    records = highest_level_records(records)
    all_attrs: set[str] = {key for record in records for key in record["attrs"]}
    single_building_attrs = {
        key
        for key in all_attrs
        if key not in SINGLE_BUILDING_ATTRIBUTE_ALLOWLIST
        and not has_any_default_weight(key)
        and not key.startswith("prod_fragments_")
        and sum(1 for record in records if abs(float(record["attrs"].get(key, 0.0))) > 1e-12) == 1
    }
    if single_building_attrs:
        all_attrs -= single_building_attrs
        for record in records:
            for key in single_building_attrs:
                record["attrs"].pop(key, None)

    attr_keys = sorted(all_attrs, key=lambda key: (0 if has_any_default_weight(key) else 1, attr_label(key), key))
    attr_keys = [
        key
        for key in attr_keys
        if any(abs(float(record["attrs"].get(key, 0.0))) > 1e-12 for record in records)
    ]
    return records, attr_keys


def normalize_value(value: float, min_value: float, max_value: float, direction: str) -> float:
    if math.isclose(max_value, min_value):
        return 0.0
    if direction == "Lower":
        return (max_value - value) / (max_value - min_value) * 100.0
    return (value - min_value) / (max_value - min_value) * 100.0


def normalize_attr_value(key: str, value: float, min_value: float, max_value: float) -> float:
    if key in SIGNED_CENTERED_ATTRS:
        scale = max(abs(min_value), abs(max_value))
        return value / scale * 100.0 if not math.isclose(scale, 0.0) else 0.0
    return normalize_value(value, min_value, max_value, direction_for_attr(key))


def normalization_max_anchor_for_attr(
    key: str,
    estimated_fp_production: float = DEFAULT_ESTIMATED_FP_PRODUCTION,
    estimated_goods_production: float = DEFAULT_ESTIMATED_GOODS_PRODUCTION,
    estimated_guild_goods_production: float = DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION,
    estimated_medal_production: float = DEFAULT_ESTIMATED_MEDAL_PRODUCTION,
) -> Optional[float]:
    if key == PROD_FP_ATTR:
        return estimated_fp_production
    if key == PROD_GOODS_ATTR:
        return estimated_goods_production
    if key == PROD_GUILD_GOODS_ATTR:
        return estimated_guild_goods_production
    if key == PROD_MEDALS_ATTR:
        return estimated_medal_production
    return None


def normalization_max_anchor_formula_for_attr(key: str) -> Optional[str]:
    if key == PROD_FP_ATTR:
        return f"{CONTROLS_SHEET_REF}!{ESTIMATED_FP_PRODUCTION_CELL}"
    if key == PROD_GOODS_ATTR:
        return f"{CONTROLS_SHEET_REF}!{ESTIMATED_GOODS_PRODUCTION_CELL}"
    if key == PROD_GUILD_GOODS_ATTR:
        return f"{CONTROLS_SHEET_REF}!{ESTIMATED_GUILD_GOODS_PRODUCTION_CELL}"
    if key == PROD_MEDALS_ATTR:
        return f"{CONTROLS_SHEET_REF}!{ESTIMATED_MEDAL_PRODUCTION_CELL}"
    return None


def effective_attr_value(
    record: Dict[str, Any],
    key: str,
    estimated_fp_production: float = DEFAULT_ESTIMATED_FP_PRODUCTION,
    estimated_goods_production: float = DEFAULT_ESTIMATED_GOODS_PRODUCTION,
    estimated_special_goods_production: float = DEFAULT_ESTIMATED_SPECIAL_GOODS_PRODUCTION,
    estimated_guild_goods_production: float = DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION,
    estimated_medal_production: float = DEFAULT_ESTIMATED_MEDAL_PRODUCTION,
) -> float:
    base = float(record["attrs"].get(key, 0.0))
    if key == PROD_FP_ATTR:
        return base + float(record["attrs"].get(BOOST_FP_ATTR, 0.0)) * estimated_fp_production / 100.0
    if key == PROD_GOODS_ATTR:
        goods_boost = float(record["attrs"].get(BOOST_GOODS_ATTR, 0.0))
        special_goods_boost = float(record["attrs"].get(BOOST_SPECIAL_GOODS_ATTR, 0.0))
        return (
            base
            + goods_boost * estimated_goods_production / 100.0
            + special_goods_boost * estimated_special_goods_production / 100.0
        )
    if key == PROD_GUILD_GOODS_ATTR:
        return base + float(record["attrs"].get(BOOST_GUILD_GOODS_ATTR, 0.0)) * estimated_guild_goods_production / 100.0
    if key == PROD_MEDALS_ATTR:
        return base + float(record["attrs"].get(BOOST_MEDALS_ATTR, 0.0)) * estimated_medal_production / 100.0
    return base


def compute_attribute_stats(records: Sequence[Dict[str, Any]], attr_keys: Sequence[str]) -> Dict[str, Dict[str, float]]:
    stats: Dict[str, Dict[str, float]] = {}
    for key in attr_keys:
        values = [effective_attr_value(record, key) for record in records]
        max_value = max(values) if values else 0.0
        max_anchor = normalization_max_anchor_for_attr(key)
        if max_anchor is not None:
            max_value = max(max_value, max_anchor)
        stats[key] = {
            "min": min(values) if values else 0.0,
            "max": max_value,
        }
    return stats


def default_score(
    record: Dict[str, Any],
    attr_keys: Sequence[str],
    stats: Dict[str, Dict[str, float]],
    weight_func=default_weight_for_attr,
) -> float:
    total_weight = 0.0
    score = 0.0
    for key in attr_keys:
        weight = weight_func(key)
        if math.isclose(weight, 0.0):
            continue
        stat = stats[key]
        norm = normalize_attr_value(key, effective_attr_value(record, key), stat["min"], stat["max"])
        score += norm * weight
        total_weight += abs(weight)
    return score / total_weight if total_weight else 0.0


def scoring_terms(
    attr_keys: Sequence[str],
    stats: Dict[str, Dict[str, float]],
    weight_func=default_weight_for_attr,
) -> Tuple[List[float], List[float], float]:
    coefficients: List[float] = []
    offsets: List[float] = []
    total_weight = 0.0
    for key in attr_keys:
        weight = weight_func(key)
        stat = stats[key]
        min_value = stat["min"]
        max_value = stat["max"]
        if math.isclose(max_value, min_value) or math.isclose(weight, 0.0):
            coefficients.append(0.0)
            offsets.append(0.0)
        elif key in SIGNED_CENTERED_ATTRS:
            scale = max(abs(min_value), abs(max_value))
            if math.isclose(scale, 0.0):
                coefficients.append(0.0)
                offsets.append(0.0)
            else:
                coefficients.append(weight * 100.0 / scale)
                offsets.append(0.0)
        elif direction_for_attr(key) == "Lower":
            coefficients.append(weight * -100.0 / (max_value - min_value))
            offsets.append(weight * max_value * 100.0 / (max_value - min_value))
        else:
            coefficients.append(weight * 100.0 / (max_value - min_value))
            offsets.append(weight * -min_value * 100.0 / (max_value - min_value))
        total_weight += abs(weight)
    return coefficients, offsets, total_weight


def formula_score_from_terms(record: Dict[str, Any], attr_keys: Sequence[str], coefficients: Sequence[float], offsets: Sequence[float], total_weight: float) -> float:
    if math.isclose(total_weight, 0.0):
        return 0.0
    weighted = sum(effective_attr_value(record, key) * coefficients[idx] for idx, key in enumerate(attr_keys))
    return (weighted + sum(offsets)) / total_weight


def building_requires_road(record: Dict[str, Any]) -> bool:
    attrs = record.get("attrs", {})
    return any(
        float(value) > 0.0
        for key, value in attrs.items()
        if is_road_connection_attr_key(key)
    )


def require_road_connection_label(record: Dict[str, Any]) -> str:
    return "Y" if building_requires_road(record) else "N"


def adjusted_area(record: Dict[str, Any]) -> float:
    area = float(record.get("area") or 0.0)
    if building_requires_road(record):
        area += 1.0
    return area


def building_category_match_formula(category_cell: str) -> str:
    return (
        f'=--OR({CONTROLS_SHEET_REF}!{BUILDING_CATEGORY_FILTER_CELL}={excel_string(ALL_BUILDING_CATEGORIES)},'
        f'{category_cell}={CONTROLS_SHEET_REF}!{BUILDING_CATEGORY_FILTER_CELL})'
    )


def build_age_records(
    entities: Dict[str, Any],
    ages: Sequence[str],
    available_only: bool,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    records_by_age: Dict[str, List[Dict[str, Any]]] = {}
    all_attrs: set[str] = set()
    for age in ages:
        records, attr_keys = collect_records(entities, age, available_only)
        records_by_age[age] = records
        all_attrs.update(attr_keys)
    attr_keys = sorted(all_attrs, key=lambda key: (0 if has_any_default_weight(key) else 1, attr_label(key), key))
    return records_by_age, attr_keys


def age_data_lookup_formula(
    entity_id: str,
    column_letter: str,
    max_row: int,
    default_value: str = "0",
) -> str:
    lookup_key = f"{excel_string(entity_id + '|')}&{CONTROLS_SHEET_REF}!{CITY_AGE_CELL}"
    return (
        f"IFERROR(INDEX({AGE_DATA_SHEET_REF}!${column_letter}$2:${column_letter}${max_row},"
        f"MATCH({lookup_key},{AGE_DATA_SHEET_REF}!$A$2:$A${max_row},0)),{default_value})"
    )


def cached_number(value: float) -> str:
    if math.isclose(value, 0.0, abs_tol=1e-12):
        return "0"
    return f"{value:.12g}"


def set_formula_cache(root: ET.Element, cell_ref: str, value: float) -> None:
    namespace = {"main": XLSX_MAIN_NS}
    cell = root.find(f".//main:c[@r='{cell_ref}']", namespace)
    if cell is None:
        return
    for value_node in list(cell.findall("main:v", namespace)):
        cell.remove(value_node)
    value_node = ET.SubElement(cell, f"{{{XLSX_MAIN_NS}}}v")
    value_node.text = cached_number(value)


def worksheet_filenames_by_title(workbook_zip: ZipFile) -> Dict[str, str]:
    namespace = {"main": XLSX_MAIN_NS, "rel": PACKAGE_REL_NS}
    workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("rel:Relationship", namespace)
        if "Id" in rel.attrib and "Target" in rel.attrib
    }

    filenames: Dict[str, str] = {}
    for sheet in workbook_root.findall("main:sheets/main:sheet", namespace):
        title = sheet.attrib.get("name")
        relation_id = sheet.attrib.get(f"{{{XLSX_REL_NS}}}id")
        target = rel_targets.get(relation_id or "")
        if not title or not target:
            continue
        if target.startswith("/"):
            filename = target.lstrip("/")
        elif target.startswith("xl/"):
            filename = target
        else:
            filename = f"xl/{target}"
        filenames[title] = filename
    return filenames


def populate_formula_caches(
    output_file: str,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
    stats: Dict[str, Dict[str, float]],
) -> None:
    if not records:
        return

    ET.register_namespace("", XLSX_MAIN_NS)
    overall_weights = overall_weight_map(attr_keys)
    overall_weight_func = lambda key: overall_weights.get(key, 0.0)
    coefficients, offsets, total_weight = scoring_terms(attr_keys, stats, overall_weight_func)
    fighting_coefficients, fighting_offsets, fighting_total_weight = scoring_terms(attr_keys, stats, fighting_weight_for_attr)
    fp_goods_coefficients, fp_goods_offsets, fp_goods_total_weight = scoring_terms(attr_keys, stats, fp_goods_weight_for_attr)
    qi_coefficients, qi_offsets, qi_total_weight = scoring_terms(attr_keys, stats, qi_weight_for_attr)
    scores = [formula_score_from_terms(record, attr_keys, coefficients, offsets, total_weight) for record in records]
    fighting_scores = [
        formula_score_from_terms(record, attr_keys, fighting_coefficients, fighting_offsets, fighting_total_weight)
        for record in records
    ]
    fp_goods_scores = [
        formula_score_from_terms(record, attr_keys, fp_goods_coefficients, fp_goods_offsets, fp_goods_total_weight)
        for record in records
    ]
    qi_scores = [
        formula_score_from_terms(record, attr_keys, qi_coefficients, qi_offsets, qi_total_weight)
        for record in records
    ]
    adjusted_areas = [adjusted_area(record) for record in records]
    overall_efficiency_scores = [
        score / area if not math.isclose(area, 0.0) else 0.0
        for score, area in zip(scores, adjusted_areas)
    ]
    fighting_efficiency_scores = [
        score / area if not math.isclose(area, 0.0) else 0.0
        for score, area in zip(fighting_scores, adjusted_areas)
    ]
    fp_goods_efficiency_scores = [
        score / area if not math.isclose(area, 0.0) else 0.0
        for score, area in zip(fp_goods_scores, adjusted_areas)
    ]
    qi_efficiency_scores = [
        score / area if not math.isclose(area, 0.0) else 0.0
        for score, area in zip(qi_scores, adjusted_areas)
    ]
    ranks = [1 + sum(1 for other_score in scores if other_score > score) for score in scores]
    fighting_ranks = [
        1 + sum(1 for other_score in fighting_scores if other_score > score)
        for score in fighting_scores
    ]
    fp_goods_ranks = [
        1 + sum(1 for other_score in fp_goods_scores if other_score > score)
        for score in fp_goods_scores
    ]
    qi_ranks = [
        1 + sum(1 for other_score in qi_scores if other_score > score)
        for score in qi_scores
    ]
    overall_efficiency_ranks = [
        1 + sum(1 for other_score in overall_efficiency_scores if other_score > score)
        for score in overall_efficiency_scores
    ]
    fighting_efficiency_ranks = [
        1 + sum(1 for other_score in fighting_efficiency_scores if other_score > score)
        for score in fighting_efficiency_scores
    ]
    fp_goods_efficiency_ranks = [
        1 + sum(1 for other_score in fp_goods_efficiency_scores if other_score > score)
        for score in fp_goods_efficiency_scores
    ]
    qi_efficiency_ranks = [
        1 + sum(1 for other_score in qi_efficiency_scores if other_score > score)
        for score in qi_efficiency_scores
    ]
    attr_columns = {key: RAW_START_COLUMN + idx for idx, key in enumerate(attr_keys)}

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".xlsx", dir=os.path.dirname(output_file))
    os.close(tmp_fd)
    try:
        with ZipFile(output_file, "r") as source, ZipFile(tmp_name, "w", ZIP_DEFLATED) as target:
            sheet_files = worksheet_filenames_by_title(source)
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == sheet_files.get(ADVANCED_CONTROLS_SHEET):
                    root = ET.fromstring(data)
                    set_formula_cache(root, OVERALL_TOTAL_WEIGHT_CELL.replace("$", ""), total_weight)
                    set_formula_cache(root, FIGHTING_TOTAL_WEIGHT_CELL.replace("$", ""), fighting_total_weight)
                    set_formula_cache(root, FP_GOODS_TOTAL_WEIGHT_CELL.replace("$", ""), fp_goods_total_weight)
                    set_formula_cache(root, QI_TOTAL_WEIGHT_CELL.replace("$", ""), qi_total_weight)
                    for idx, key in enumerate(attr_keys):
                        row = WEIGHT_START_ROW + idx
                        set_formula_cache(root, f"C{row}", overall_weights.get(key, 0.0))
                        set_formula_cache(root, f"D{row}", abs(overall_weights.get(key, 0.0)))
                        if isinstance(overall_raw_weight_cell_value(key), str):
                            set_formula_cache(root, f"{get_column_letter(OVERALL_RAW_WEIGHT_COLUMN)}{row}", overall_raw_weight_for_attr(key))
                        set_formula_cache(root, f"E{row}", fighting_weight_for_attr(key))
                        set_formula_cache(root, f"F{row}", abs(fighting_weight_for_attr(key)))
                        set_formula_cache(root, f"G{row}", fp_goods_weight_for_attr(key))
                        set_formula_cache(root, f"H{row}", abs(fp_goods_weight_for_attr(key)))
                        set_formula_cache(root, f"I{row}", qi_weight_for_attr(key))
                        set_formula_cache(root, f"J{row}", abs(qi_weight_for_attr(key)))
                        if key in {PROD_FP_ATTR, PROD_GOODS_ATTR, PROD_GUILD_GOODS_ATTR, PROD_MEDALS_ATTR}:
                            set_formula_cache(root, f"L{row}", stats[key]["min"])
                            set_formula_cache(root, f"M{row}", stats[key]["max"])
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(OVERALL_SOURCE_SHEET):
                    root = ET.fromstring(data)
                    raw_start = RAW_START_COLUMN
                    for idx, value in enumerate(coefficients):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}2", value)
                    for idx, value in enumerate(offsets):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}3", value)
                    for idx, value in enumerate(fighting_coefficients):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}4", value)
                    for idx, value in enumerate(fighting_offsets):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}5", value)
                    for idx, value in enumerate(fp_goods_coefficients):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}6", value)
                    for idx, value in enumerate(fp_goods_offsets):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}7", value)
                    for idx, value in enumerate(qi_coefficients):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}8", value)
                    for idx, value in enumerate(qi_offsets):
                        set_formula_cache(root, f"{get_column_letter(raw_start + idx)}9", value)
                    for idx, score in enumerate(scores):
                        row = BUILDING_DATA_START_ROW + idx
                        set_formula_cache(root, f"B{row}", ranks[idx])
                        set_formula_cache(root, f"C{row}", score)
                        for key in (PROD_FP_ATTR, PROD_GOODS_ATTR, PROD_GUILD_GOODS_ATTR, PROD_MEDALS_ATTR):
                            if key in attr_columns:
                                set_formula_cache(
                                    root,
                                    f"{get_column_letter(attr_columns[key])}{row}",
                                    effective_attr_value(records[idx], key),
                                )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(OVERALL_SCORE_SHEET):
                    root = ET.fromstring(data)
                    for idx, score in enumerate(scores, start=2):
                        set_formula_cache(root, f"A{idx}", BUILDING_DATA_START_ROW + idx - 2)
                        set_formula_cache(root, f"B{idx}", score)
                        set_formula_cache(root, f"C{idx}", ranks[idx - 2])
                        set_formula_cache(root, f"D{idx}", adjusted_areas[idx - 2])
                        set_formula_cache(root, f"E{idx}", overall_efficiency_scores[idx - 2])
                        set_formula_cache(root, f"F{idx}", overall_efficiency_ranks[idx - 2])
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(OVERALL_EFFICIENCY_SHEET):
                    root = ET.fromstring(data)
                    display_attr_keys = [
                        key
                        for key in overall_ranking_display_attr_keys(attr_keys)
                        if not is_road_connection_attr_key(key)
                    ]
                    attr_start = 9
                    source_row_col = attr_start + len(display_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-overall_efficiency_scores[record_idx], record_idx),
                    )[:OVERALL_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", overall_efficiency_scores[record_idx])
                        set_formula_cache(root, f"D{output_idx}", scores[record_idx])
                        set_formula_cache(root, f"G{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"H{output_idx}", adjusted_areas[record_idx])
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(display_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                display_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(FIGHTING_SCORE_SHEET):
                    root = ET.fromstring(data)
                    for idx, score in enumerate(fighting_scores, start=2):
                        set_formula_cache(root, f"A{idx}", BUILDING_DATA_START_ROW + idx - 2)
                        set_formula_cache(root, f"B{idx}", score)
                        set_formula_cache(root, f"C{idx}", fighting_ranks[idx - 2])
                        set_formula_cache(root, f"D{idx}", adjusted_areas[idx - 2])
                        set_formula_cache(root, f"E{idx}", fighting_efficiency_scores[idx - 2])
                        set_formula_cache(root, f"F{idx}", fighting_efficiency_ranks[idx - 2])
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get("Fighting Ranking"):
                    root = ET.fromstring(data)
                    fighting_attr_keys = [key for key in attr_keys if fighting_weight_for_attr(key)]
                    attr_start = 7
                    source_row_col = attr_start + len(fighting_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-fighting_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", fighting_scores[record_idx])
                        set_formula_cache(root, f"F{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(fighting_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(FIGHTING_EFFICIENCY_SHEET):
                    root = ET.fromstring(data)
                    fighting_attr_keys = [key for key in attr_keys if fighting_weight_for_attr(key)]
                    attr_start = 9
                    source_row_col = attr_start + len(fighting_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-fighting_efficiency_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", fighting_efficiency_scores[record_idx])
                        set_formula_cache(root, f"D{output_idx}", fighting_scores[record_idx])
                        set_formula_cache(root, f"G{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"H{output_idx}", adjusted_areas[record_idx])
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(fighting_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(FP_GOODS_SCORE_SHEET):
                    root = ET.fromstring(data)
                    for idx, score in enumerate(fp_goods_scores, start=2):
                        set_formula_cache(root, f"A{idx}", BUILDING_DATA_START_ROW + idx - 2)
                        set_formula_cache(root, f"B{idx}", score)
                        set_formula_cache(root, f"C{idx}", fp_goods_ranks[idx - 2])
                        set_formula_cache(root, f"D{idx}", adjusted_areas[idx - 2])
                        set_formula_cache(root, f"E{idx}", fp_goods_efficiency_scores[idx - 2])
                        set_formula_cache(root, f"F{idx}", fp_goods_efficiency_ranks[idx - 2])
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(FP_GOODS_PRODUCTION_SHEET):
                    root = ET.fromstring(data)
                    production_attr_keys = fp_goods_display_attr_keys(attr_keys)
                    attr_start = 7
                    source_row_col = attr_start + len(production_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-fp_goods_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", fp_goods_scores[record_idx])
                        set_formula_cache(root, f"F{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(production_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(FP_GOODS_EFFICIENCY_SHEET):
                    root = ET.fromstring(data)
                    production_attr_keys = fp_goods_display_attr_keys(attr_keys)
                    attr_start = 9
                    source_row_col = attr_start + len(production_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-fp_goods_efficiency_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", fp_goods_efficiency_scores[record_idx])
                        set_formula_cache(root, f"D{output_idx}", fp_goods_scores[record_idx])
                        set_formula_cache(root, f"G{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"H{output_idx}", adjusted_areas[record_idx])
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(production_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(QI_SCORE_SHEET):
                    root = ET.fromstring(data)
                    for idx, score in enumerate(qi_scores, start=2):
                        set_formula_cache(root, f"A{idx}", BUILDING_DATA_START_ROW + idx - 2)
                        set_formula_cache(root, f"B{idx}", score)
                        set_formula_cache(root, f"C{idx}", qi_ranks[idx - 2])
                        set_formula_cache(root, f"D{idx}", adjusted_areas[idx - 2])
                        set_formula_cache(root, f"E{idx}", qi_efficiency_scores[idx - 2])
                        set_formula_cache(root, f"F{idx}", qi_efficiency_ranks[idx - 2])
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(QI_RANKING_SHEET):
                    root = ET.fromstring(data)
                    qi_attr_keys = qi_display_attr_keys(attr_keys)
                    attr_start = 7
                    source_row_col = attr_start + len(qi_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-qi_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", qi_scores[record_idx])
                        set_formula_cache(root, f"F{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(qi_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                elif item.filename == sheet_files.get(QI_EFFICIENCY_SHEET):
                    root = ET.fromstring(data)
                    qi_attr_keys = qi_display_attr_keys(attr_keys)
                    attr_start = 9
                    source_row_col = attr_start + len(qi_attr_keys) + 4
                    top_indices = sorted(
                        range(len(records)),
                        key=lambda record_idx: (-qi_efficiency_scores[record_idx], record_idx),
                    )[:FIGHTING_TOP_N]
                    for output_idx, record_idx in enumerate(top_indices, start=5):
                        source_row = BUILDING_DATA_START_ROW + record_idx
                        record = records[record_idx]
                        set_formula_cache(root, f"B{output_idx}", output_idx - 4)
                        set_formula_cache(root, f"C{output_idx}", qi_efficiency_scores[record_idx])
                        set_formula_cache(root, f"D{output_idx}", qi_scores[record_idx])
                        set_formula_cache(root, f"G{output_idx}", float(record["area"] or 0))
                        set_formula_cache(root, f"H{output_idx}", adjusted_areas[record_idx])
                        set_formula_cache(root, f"{get_column_letter(source_row_col)}{output_idx}", source_row)
                        for attr_idx, key in enumerate(qi_attr_keys, start=attr_start):
                            set_formula_cache(
                                root,
                                f"{get_column_letter(attr_idx)}{output_idx}",
                                effective_attr_value(record, key),
                            )
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(item, data)
        os.replace(tmp_name, output_file)
        os.chmod(output_file, 0o644)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def write_controls_sheet(
    workbook: Workbook,
    reference_file: str,
    era: str,
    available_only: bool,
    all_ages: bool = False,
    category_options: Sequence[str] = (),
) -> None:
    sheet = workbook.active
    sheet.title = CONTROLS_SHEET
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 115

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    editable_fill = PatternFill("solid", fgColor=EDITABLE_FILL_COLOR)
    slider_fill = PatternFill("solid", fgColor=SLIDER_FILL_COLOR)
    slider_selected_fill = PatternFill("solid", fgColor=SLIDER_SELECTED_FILL_COLOR)
    context_fill = PatternFill("solid", fgColor=CONTROL_CONTEXT_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    track_side = Side(style="medium", color="79A878")
    no_side = Side(style=None)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    sheet["A1"] = (
        "Interactive Building Rankings - All Ages - Main Controls"
        if all_ages
        else "Building Attribute Ranking Main Controls - Scale Values 1-5"
    )
    sheet["A1"].font = Font(bold=True, size=18, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet["A1"].alignment = Alignment(vertical="center")
    sheet.merge_cells("A1:G1")
    sheet.row_dimensions[1].height = 30

    rows = [
        (
            2,
            "How to use",
            "Start here: pick your city age, select a building source category filter, then enter your city’s estimated base production for FP, regular goods, guild goods, medals, and special goods in the yellow cells. These values should not include any percentage-based boosts.\n\nNext, choose the Fighting, QI, and FP/Goods Production focus settings that best match your priorities. For each 1–5 scale, 1 favors the left label, 3 is balanced, and 5 favors the right label.\n\nThen review the ranking sheets.",
            PatternFill(fill_type=None),
        ),
        (3, "Select Your City Age" if all_ages else "Assumed age", selected_age_display(era, all_ages), editable_fill if all_ages else context_fill),
        (5, "Building source category filter", ALL_BUILDING_CATEGORIES, editable_fill),
        (6, "Estimated base FP production", DEFAULT_ESTIMATED_FP_PRODUCTION, editable_fill),
        (7, "Estimated base regular goods production", DEFAULT_ESTIMATED_GOODS_PRODUCTION, editable_fill),
        (8, "Estimated base guild goods production", DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION, editable_fill),
        (9, "Estimated base medal production", DEFAULT_ESTIMATED_MEDAL_PRODUCTION, editable_fill),
        (10, "QI fighter role", "Both", editable_fill),
        (11, "Estimated base special goods production", DEFAULT_ESTIMATED_SPECIAL_GOODS_PRODUCTION, editable_fill),
    ]
    for row_idx, label, value, fill in rows:
        sheet.cell(row_idx, 1, label)
        sheet.cell(row_idx, 2, value)
        sheet.cell(row_idx, 1).font = Font(size=12, color=HEADER_FONT_COLOR)
        sheet.cell(row_idx, 2).font = Font(size=12, color=TITLE_FONT_COLOR)
        sheet.cell(row_idx, 1).border = border
        sheet.cell(row_idx, 2).border = border
        sheet.cell(row_idx, 2).fill = fill
        sheet.cell(row_idx, 1).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(row_idx, 2).alignment = Alignment(vertical="top", wrap_text=label == "How to use")
        if label.startswith("Estimated base"):
            sheet.cell(row_idx, 2).number_format = "#,##0"
    sheet.merge_cells("B2:G2")
    sheet.row_dimensions[2].height = 120
    if all_ages:
        age_start_row = 1
        age_end_row = len(AGE_ORDER)
        age_list_range = f"'{AGE_OPTIONS_SHEET}'!$A${age_start_row}:$A${age_end_row}"
        workbook.defined_names.add(
            DefinedName(CITY_AGE_LIST_NAME, attr_text=age_list_range)
        )
        age_dv = DataValidation(type="list", formula1=age_list_range, allow_blank=False)
        age_dv.showDropDown = False
        age_dv.showInputMessage = True
        age_dv.showErrorMessage = True
        age_dv.errorStyle = "stop"
        age_dv.promptTitle = "Select Your City Age"
        age_dv.prompt = "Pick the age to use for ranking data."
        age_dv.errorTitle = "Use the dropdown"
        age_dv.error = "Choose a city age from the dropdown list."
        sheet.add_data_validation(age_dv)
        age_dv.add(CITY_AGE_CELL)
    if category_options:
        category_start_row = 1
        category_end_row = len(category_options)
        category_list_range = f"'{CATEGORY_OPTIONS_SHEET}'!$A${category_start_row}:$A${category_end_row}"
        workbook.defined_names.add(
            DefinedName(BUILDING_CATEGORY_LIST_NAME, attr_text=category_list_range)
        )
        category_dv = DataValidation(type="list", formula1=category_list_range, allow_blank=False)
        category_dv.showDropDown = False
        category_dv.showInputMessage = True
        category_dv.showErrorMessage = True
        category_dv.errorStyle = "stop"
        category_dv.promptTitle = "Building source category filter"
        category_dv.prompt = "Pick a category to show in the ranking sheets."
        category_dv.errorTitle = "Use the dropdown"
        category_dv.error = "Choose a building category from the dropdown list."
        sheet.add_data_validation(category_dv)
        category_dv.add(BUILDING_CATEGORY_FILTER_CELL)

    def add_focus_selector(
        row_idx: int,
        title: str,
        input_cell_ref: str,
        default_value: int,
        slider_labels: Sequence[str],
    ) -> None:
        sheet.cell(row_idx, 1, title)
        sheet.cell(row_idx, 1).font = Font(size=12, color=HEADER_FONT_COLOR)
        sheet.cell(row_idx, 1).border = border
        sheet.cell(row_idx, 1).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(row_idx, 2, "Selected scale")
        sheet.cell(row_idx, 2).font = Font(size=12, color=HEADER_FONT_COLOR)
        sheet.cell(row_idx, 2).fill = slider_fill
        sheet.cell(row_idx, 2).border = border
        sheet.cell(row_idx, 2).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet[input_cell_ref] = default_value
        sheet[input_cell_ref].font = Font(bold=True, size=12, color=TITLE_FONT_COLOR)
        sheet[input_cell_ref].fill = editable_fill
        sheet[input_cell_ref].border = border
        sheet[input_cell_ref].alignment = Alignment(horizontal="center", vertical="center")
        sheet[input_cell_ref].number_format = "0"
        track_labels = [slider_labels[0], "", slider_labels[2], "", slider_labels[4]]
        for offset, label in enumerate(track_labels, start=3):
            label_cell = sheet.cell(row_idx, offset, label)
            value_cell = sheet.cell(row_idx + 1, offset, offset - 2)
            label_cell.font = Font(size=12, color=TITLE_FONT_COLOR)
            label_cell.alignment = Alignment(horizontal="center", vertical="bottom", wrap_text=True)
            value_cell.border = Border(
                left=track_side if offset == 3 else no_side,
                right=track_side if offset == 7 else no_side,
                top=track_side,
                bottom=track_side,
            )
            value_cell.fill = slider_fill
            value_cell.alignment = Alignment(horizontal="center", vertical="center")
            value_cell.font = Font(bold=True, size=12, color=TITLE_FONT_COLOR)
            scale_value = offset - 2
            sheet.conditional_formatting.add(
                f"{get_column_letter(offset)}{row_idx + 1}:{get_column_letter(offset)}{row_idx + 1}",
                FormulaRule(formula=[f"{input_cell_ref}={scale_value}"], fill=slider_selected_fill),
            )

    add_focus_selector(
        12,
        "Fighting GBG/GE focus",
        FIGHTING_GBG_GE_FOCUS_CELL,
        DEFAULT_FIGHTING_GBG_GE_FOCUS,
        ["GBG only", "Mostly GBG", "Half and half", "Mostly GE", "GE only"],
    )
    add_focus_selector(
        14,
        "Fighting Red/Blue focus",
        FIGHTING_RED_BLUE_FOCUS_CELL,
        DEFAULT_FIGHTING_RED_BLUE_FOCUS,
        ["Red only", "Mostly Red", "Half and half", "Mostly Blue", "Blue only"],
    )
    add_focus_selector(
        16,
        "Fighting Attack/Defense focus",
        FIGHTING_ATTACK_DEFENSE_FOCUS_CELL,
        DEFAULT_FIGHTING_ATTACK_DEFENSE_FOCUS,
        ["Attack only", "Mostly attack", "Half and half", "Mostly defense", "Defense only"],
    )
    add_focus_selector(
        18,
        "Fighting Current/Next Age unit focus",
        FIGHTING_UNIT_AGE_FOCUS_CELL,
        DEFAULT_FIGHTING_UNIT_AGE_FOCUS,
        ["Current only", "Mostly current", "Half and half", "Mostly next", "Next only"],
    )
    add_focus_selector(
        20,
        "Production FP/Goods focus",
        PRODUCTION_FP_GOODS_FOCUS_CELL,
        DEFAULT_PRODUCTION_FP_GOODS_FOCUS,
        ["FP only", "Mostly FP", "Half and half", "Mostly goods", "Goods only"],
    )
    focus_dv = DataValidation(type="list", formula1='"1,2,3,4,5"', allow_blank=False)
    sheet.add_data_validation(focus_dv)
    focus_dv.add(FIGHTING_GBG_GE_FOCUS_CELL)
    focus_dv.add(FIGHTING_RED_BLUE_FOCUS_CELL)
    focus_dv.add(FIGHTING_UNIT_AGE_FOCUS_CELL)
    focus_dv.add(FIGHTING_ATTACK_DEFENSE_FOCUS_CELL)
    focus_dv.add(PRODUCTION_FP_GOODS_FOCUS_CELL)

    role_dv = DataValidation(type="list", formula1='"Both,Blue,Red"', allow_blank=False)
    sheet.add_data_validation(role_dv)
    role_dv.add(QI_FIGHTER_ROLE_CELL)

    sheet.row_dimensions[10].height = 24
    for row_idx in (12, 14, 16, 18, 20):
        sheet.row_dimensions[row_idx].height = 36
        sheet.row_dimensions[row_idx + 1].height = 28

    sheet.column_dimensions["A"].width = 48
    sheet.column_dimensions["B"].width = 20
    for column in ("C", "D", "E", "F", "G"):
        sheet.column_dimensions[column].width = 16


def write_advanced_controls_sheet(
    workbook: Workbook,
    reference_file: str,
    era: str,
    attr_keys: Sequence[str],
    stats: Dict[str, Dict[str, float]],
    available_only: bool,
    record_count: int,
    all_ages: bool = False,
) -> None:
    sheet = workbook.create_sheet(ADVANCED_CONTROLS_SHEET)
    sheet.sheet_view.showGridLines = False

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    editable_fill = PatternFill("solid", fgColor=EDITABLE_FILL_COLOR)
    context_fill = PatternFill("solid", fgColor=CONTROL_CONTEXT_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    sheet["A1"] = "Advanced Building Attribute Ranking Controls"
    sheet["A1"].font = Font(bold=True, size=16, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=QI_WEIGHT_OVERRIDE_COLUMN)

    rows = [
        ("Selected city age" if all_ages else "Assumed age", f"={CONTROLS_SHEET_REF}!{CITY_AGE_CELL}" if all_ages else era),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("How to use", f"Optional fine tuning: keep Weight mode as Default to use generated weights, or switch to Custom and enter yellow override values in the right-side override columns. Set Weight mode back to Default to restore all generated defaults. After changes, review {OVERALL_RANKING_SHEET} or the focused ranking sheets."),
    ]
    for idx, (label, value) in enumerate(rows, start=2):
        sheet.cell(idx, 1, label)
        sheet.cell(idx, 2, value)
        sheet.cell(idx, 1).font = Font(bold=True)
        sheet.cell(idx, 2).fill = (
            context_fill
            if "age" in label.lower()
            else PatternFill(fill_type=None)
        )
        sheet.cell(idx, 2).alignment = Alignment(vertical="top", wrap_text=label == "How to use")
    sheet.merge_cells(start_row=4, start_column=2, end_row=4, end_column=QI_WEIGHT_OVERRIDE_COLUMN)
    sheet["B4"].alignment = Alignment(vertical="top", wrap_text=True)
    sheet.row_dimensions[4].height = 45
    sheet["A5"] = "Total active weight"
    sheet["A5"].font = Font(bold=True)
    total_headers = (
        (OVERALL_TOTAL_WEIGHT_CELL, "Overall"),
        (FIGHTING_TOTAL_WEIGHT_CELL, "Fighting"),
        (FP_GOODS_TOTAL_WEIGHT_CELL, "Farming"),
        (QI_TOTAL_WEIGHT_CELL, "QI"),
    )
    for total_cell, header in total_headers:
        col_idx = sheet[total_cell].column
        cell = sheet.cell(5, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="right")
    sheet["A7"] = "Weight mode"
    sheet["B7"] = "Default"
    sheet["C7"] = "Default restores all generated weights. Custom uses nonblank values from the override columns."
    sheet["A7"].font = Font(bold=True)
    sheet[ADVANCED_WEIGHT_MODE_CELL].fill = editable_fill
    sheet[ADVANCED_WEIGHT_MODE_CELL].border = border
    sheet[ADVANCED_WEIGHT_MODE_CELL].alignment = Alignment(vertical="top", wrap_text=True)
    sheet["C7"].alignment = Alignment(vertical="top", wrap_text=True)
    sheet.merge_cells(start_row=7, start_column=3, end_row=7, end_column=QI_WEIGHT_OVERRIDE_COLUMN)
    sheet[OVERALL_TOTAL_WEIGHT_CELL] = f"=SUM(D{WEIGHT_START_ROW}:D1048576)"
    sheet[FIGHTING_TOTAL_WEIGHT_CELL] = f"=SUM(F{WEIGHT_START_ROW}:F1048576)"
    sheet[FP_GOODS_TOTAL_WEIGHT_CELL] = f"=SUM(H{WEIGHT_START_ROW}:H1048576)"
    sheet[QI_TOTAL_WEIGHT_CELL] = f"=SUM(J{WEIGHT_START_ROW}:J1048576)"
    sheet[OVERALL_TOTAL_WEIGHT_CELL].font = Font(bold=True)
    sheet[FIGHTING_TOTAL_WEIGHT_CELL].font = Font(bold=True)
    sheet[FP_GOODS_TOTAL_WEIGHT_CELL].font = Font(bold=True)
    sheet[QI_TOTAL_WEIGHT_CELL].font = Font(bold=True)

    mode_dv = DataValidation(type="list", formula1='"Default,Custom"', allow_blank=False)
    mode_dv.showDropDown = False
    mode_dv.showInputMessage = True
    mode_dv.showErrorMessage = True
    mode_dv.errorStyle = "stop"
    mode_dv.promptTitle = "Weight mode"
    mode_dv.prompt = "Default restores generated weights. Custom uses nonblank override cells."
    mode_dv.errorTitle = "Use Default or Custom"
    mode_dv.error = "Choose Default or Custom from the dropdown."
    sheet.add_data_validation(mode_dv)
    mode_dv.add(ADVANCED_WEIGHT_MODE_CELL)

    header_row = WEIGHT_HEADER_ROW
    headers = [
        "Attribute",
        "Description",
        "Overall Weight",
        "Overall Abs Weight",
        "Fighting Weight",
        "Fighting Abs Weight",
        "Farming Weight",
        "Farming Abs Weight",
        "QI Weight",
        "QI Abs Weight",
        "Direction",
        "Min",
        "Max",
        "Overall Raw Weight",
        "Overall Weight Group",
        "Overall Weight Budget",
        "Overall Override",
        "Fighting Override",
        "Farming Override",
        "QI Override",
    ]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, key in enumerate(attr_keys, start=WEIGHT_START_ROW):
        attr_idx = row_idx - WEIGHT_START_ROW
        raw_col = get_column_letter(RAW_START_COLUMN + attr_idx)
        data_end = BUILDING_DATA_START_ROW + record_count - 1
        label = attr_label(key)
        force_zero_weight = is_forced_zero_weight_attr(key)
        sheet.cell(row_idx, 1, label)
        sheet.cell(row_idx, 2, attr_description(key))
        sheet.cell(row_idx, 2).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(
            row_idx,
            3,
            0 if force_zero_weight else weight_mode_formula(overall_weight_cell_value(row_idx), OVERALL_WEIGHT_OVERRIDE_COLUMN, row_idx),
        )
        sheet.cell(row_idx, 4, f"=ABS(C{row_idx})")
        sheet.cell(
            row_idx,
            5,
            0 if force_zero_weight else weight_mode_formula(fighting_weight_cell_value(key), FIGHTING_WEIGHT_OVERRIDE_COLUMN, row_idx),
        )
        sheet.cell(row_idx, 6, f"=ABS(E{row_idx})")
        sheet.cell(
            row_idx,
            7,
            0 if force_zero_weight else weight_mode_formula(fp_goods_weight_cell_value(key), FP_GOODS_WEIGHT_OVERRIDE_COLUMN, row_idx),
        )
        sheet.cell(row_idx, 8, f"=ABS(G{row_idx})")
        sheet.cell(
            row_idx,
            9,
            0 if force_zero_weight else weight_mode_formula(qi_role_weight_formula(key) or qi_weight_for_attr(key), QI_WEIGHT_OVERRIDE_COLUMN, row_idx),
        )
        sheet.cell(row_idx, 10, f"=ABS(I{row_idx})")
        sheet.cell(row_idx, 11, direction_for_attr(key))
        if (all_ages or key in {PROD_FP_ATTR, PROD_GOODS_ATTR, PROD_GUILD_GOODS_ATTR, PROD_MEDALS_ATTR}) and record_count:
            sheet.cell(row_idx, 12, f"=MIN('{OVERALL_SOURCE_SHEET}'!${raw_col}${BUILDING_DATA_START_ROW}:${raw_col}${data_end})")
            max_formula = f"MAX('{OVERALL_SOURCE_SHEET}'!${raw_col}${BUILDING_DATA_START_ROW}:${raw_col}${data_end})"
            max_anchor_formula = normalization_max_anchor_formula_for_attr(key)
            if max_anchor_formula:
                max_formula = f"MAX({max_formula},{max_anchor_formula})"
            sheet.cell(row_idx, 13, f"={max_formula}")
        else:
            sheet.cell(row_idx, 12, numeric_cell(stats[key]["min"]))
            sheet.cell(row_idx, 13, numeric_cell(stats[key]["max"]))
        sheet.cell(row_idx, OVERALL_RAW_WEIGHT_COLUMN, 0 if force_zero_weight else overall_raw_weight_cell_value(key))
        weight_group = overall_weight_group_for_attr(key)
        sheet.cell(row_idx, OVERALL_WEIGHT_GROUP_COLUMN, weight_group)
        sheet.cell(row_idx, OVERALL_WEIGHT_BUDGET_COLUMN, overall_weight_budget_cell_value(weight_group))
        for col_idx in range(1, QI_WEIGHT_OVERRIDE_COLUMN + 1):
            cell = sheet.cell(row_idx, col_idx)
            cell.border = border
            if col_idx == 2:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            if col_idx in (
                OVERALL_WEIGHT_OVERRIDE_COLUMN,
                FIGHTING_WEIGHT_OVERRIDE_COLUMN,
                FP_GOODS_WEIGHT_OVERRIDE_COLUMN,
                QI_WEIGHT_OVERRIDE_COLUMN,
            ):
                cell.fill = editable_fill
            if col_idx in (
                3,
                4,
                5,
                6,
                7,
                8,
                9,
                10,
                12,
                13,
                OVERALL_RAW_WEIGHT_COLUMN,
                OVERALL_WEIGHT_BUDGET_COLUMN,
                OVERALL_WEIGHT_OVERRIDE_COLUMN,
                FIGHTING_WEIGHT_OVERRIDE_COLUMN,
                FP_GOODS_WEIGHT_OVERRIDE_COLUMN,
                QI_WEIGHT_OVERRIDE_COLUMN,
            ):
                cell.number_format = "0.00"
        if force_zero_weight:
            sheet.row_dimensions[row_idx].hidden = True

    for row_idx in range(WEIGHT_START_ROW, WEIGHT_HEADER_ROW + len(attr_keys) + 1):
        sheet.cell(row_idx, 2).alignment = Alignment(vertical="top", wrap_text=True)

    dv = DataValidation(type="decimal", operator="between", formula1="-1000", formula2="1000")
    sheet.add_data_validation(dv)
    if attr_keys:
        dv.add(f"{get_column_letter(OVERALL_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_START_ROW}:{get_column_letter(OVERALL_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_HEADER_ROW + len(attr_keys)}")
        dv.add(f"{get_column_letter(FIGHTING_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_START_ROW}:{get_column_letter(FIGHTING_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_HEADER_ROW + len(attr_keys)}")
        dv.add(f"{get_column_letter(FP_GOODS_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_START_ROW}:{get_column_letter(FP_GOODS_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_HEADER_ROW + len(attr_keys)}")
        dv.add(f"{get_column_letter(QI_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_START_ROW}:{get_column_letter(QI_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_HEADER_ROW + len(attr_keys)}")
    sheet.freeze_panes = f"A{WEIGHT_START_ROW}"
    sheet.auto_filter.ref = f"A{WEIGHT_HEADER_ROW}:{get_column_letter(QI_WEIGHT_OVERRIDE_COLUMN)}{WEIGHT_HEADER_ROW + len(attr_keys)}"
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 92
    sheet.column_dimensions["C"].width = 12
    sheet.column_dimensions["D"].width = 12
    sheet.column_dimensions["E"].width = 12
    sheet.column_dimensions["F"].width = 12
    sheet.column_dimensions["G"].width = 12
    sheet.column_dimensions["H"].width = 12
    sheet.column_dimensions["I"].width = 12
    sheet.column_dimensions["J"].width = 12
    sheet.column_dimensions["K"].width = 12
    sheet.column_dimensions["L"].width = 14
    sheet.column_dimensions["M"].width = 14
    sheet.column_dimensions[get_column_letter(OVERALL_RAW_WEIGHT_COLUMN)].width = 16
    sheet.column_dimensions[get_column_letter(OVERALL_WEIGHT_GROUP_COLUMN)].width = 18
    sheet.column_dimensions[get_column_letter(OVERALL_WEIGHT_BUDGET_COLUMN)].width = 18
    sheet.column_dimensions[get_column_letter(OVERALL_WEIGHT_OVERRIDE_COLUMN)].width = 16
    sheet.column_dimensions[get_column_letter(FIGHTING_WEIGHT_OVERRIDE_COLUMN)].width = 16
    sheet.column_dimensions[get_column_letter(FP_GOODS_WEIGHT_OVERRIDE_COLUMN)].width = 16
    sheet.column_dimensions[get_column_letter(QI_WEIGHT_OVERRIDE_COLUMN)].width = 16
    sheet.column_dimensions["D"].hidden = True
    sheet.column_dimensions["F"].hidden = True
    sheet.column_dimensions["H"].hidden = True
    sheet.column_dimensions["J"].hidden = True
    sheet.column_dimensions[get_column_letter(OVERALL_RAW_WEIGHT_COLUMN)].hidden = True
    sheet.column_dimensions[get_column_letter(OVERALL_WEIGHT_GROUP_COLUMN)].hidden = True
    sheet.column_dimensions[get_column_letter(OVERALL_WEIGHT_BUDGET_COLUMN)].hidden = True
    for row in sheet.iter_rows(min_row=2, max_row=7, min_col=1, max_col=QI_WEIGHT_OVERRIDE_COLUMN):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet["B4"].alignment = Alignment(vertical="top", wrap_text=True)
    for total_cell, _header in total_headers:
        sheet.cell(5, sheet[total_cell].column).alignment = Alignment(horizontal="right", vertical="top", wrap_text=True)


def write_age_data_sheet(
    workbook: Workbook,
    records_by_age: Dict[str, List[Dict[str, Any]]],
    attr_keys: Sequence[str],
) -> Dict[str, Any]:
    sheet = workbook.create_sheet(AGE_DATA_SHEET)
    sheet.sheet_state = "hidden"
    headers = [
        "Lookup Key",
        "Entity ID",
        "Selected Age",
        "Size",
        REQUIRE_ROAD_HEADER,
        "Area",
        "Available By Age",
        "Environment Effect",
        "Fragment / Reward Production",
    ] + [attr_label(key) for key in attr_keys]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_idx = 2
    for age in AGE_ORDER:
        for record in records_by_age.get(age, []):
            base_values = [
                age_lookup_key(str(record["entity_id"]), age),
                record["entity_id"],
                age_display_name(age),
                record["size"],
                require_road_connection_label(record),
                numeric_cell(record["area"]) if record["area"] is not None else "",
                record["available"],
                record["environment_effect"],
                record["reward_production"],
            ]
            for col_idx, value in enumerate(base_values, start=1):
                sheet.cell(row_idx, col_idx, value)
            for attr_idx, key in enumerate(attr_keys, start=10):
                sheet.cell(row_idx, attr_idx, numeric_cell(float(record["attrs"].get(key, 0.0))))
            row_idx += 1

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(row_idx - 1, 1)}"
    sheet.column_dimensions["A"].width = 42
    sheet.column_dimensions["B"].width = 28
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 10
    sheet.column_dimensions["E"].width = 20
    sheet.column_dimensions["F"].width = 10
    sheet.column_dimensions["G"].width = 17
    sheet.column_dimensions["H"].width = 48
    sheet.column_dimensions["I"].width = 92
    for col_idx in range(10, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18

    return {
        "max_row": max(row_idx - 1, 2),
        "size_col": "D",
        "road_col": "E",
        "area_col": "F",
        "available_col": "G",
        "environment_col": "H",
        "reward_col": "I",
        "attr_columns": {key: get_column_letter(10 + idx) for idx, key in enumerate(attr_keys)},
    }


def write_age_options_sheet(workbook: Workbook) -> None:
    sheet = workbook.create_sheet(AGE_OPTIONS_SHEET)
    sheet.sheet_state = "hidden"
    for row_idx, age in enumerate(AGE_ORDER, start=1):
        sheet.cell(row_idx, 1, age_display_name(age))
    sheet.column_dimensions["A"].width = 28


def write_category_options_sheet(workbook: Workbook, category_options: Sequence[str]) -> None:
    sheet = workbook.create_sheet(CATEGORY_OPTIONS_SHEET)
    sheet.sheet_state = "hidden"
    for row_idx, category in enumerate(category_options, start=1):
        sheet.cell(row_idx, 1, category)
    sheet.column_dimensions["A"].width = 36


def write_goods_resource_audit_sheet(workbook: Workbook, attr_keys: Sequence[str]) -> None:
    sheet = workbook.create_sheet(GOODS_RESOURCE_AUDIT_SHEET)
    sheet.sheet_state = "hidden"
    sheet.sheet_view.showGridLines = False
    headers = ["Resource Key", "Classification", "Discovered In", "Notes"]
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_idx, row_values in enumerate(goods_resource_audit_rows(attr_keys), start=2):
        for col_idx, value in enumerate(row_values, start=1):
            cell = sheet.cell(row_idx, col_idx, value)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    widths = [32, 34, 24, 72]
    for col_idx, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = width
    sheet.freeze_panes = "A2"


def write_buildings_sheet(
    workbook: Workbook,
    records: List[Dict[str, Any]],
    attr_keys: Sequence[str],
    stats: Dict[str, Dict[str, float]],
    age_data_context: Optional[Dict[str, Any]] = None,
) -> None:
    sheet = workbook.create_sheet(OVERALL_SOURCE_SHEET)
    sheet.sheet_state = "hidden"
    sheet.sheet_view.showGridLines = False

    base_headers = [
        "Building",
        "Overall Rank",
        "Overall Score",
        "Size",
        REQUIRE_ROAD_HEADER,
        "Area",
    ]
    metadata_headers = [
        "Type",
        "Selected Age",
        "Available By Age",
        "Building Category",
        "Environment Effect",
        "Entity ID",
        "Fragment / Reward Production",
    ]
    raw_headers = [attr_label(key) for key in attr_keys]

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    sheet["A1"] = OVERALL_RANKING_SHEET
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(base_headers) + len(raw_headers) + len(metadata_headers))

    coefficient_row = 2
    offset_row = 3
    fighting_coefficient_row = 4
    fighting_offset_row = 5
    fp_goods_coefficient_row = 6
    fp_goods_offset_row = 7
    qi_coefficient_row = 8
    qi_offset_row = 9
    header_row = BUILDING_HEADER_ROW
    all_headers = base_headers + raw_headers + metadata_headers
    for col_idx, header in enumerate(all_headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    raw_start = len(base_headers) + 1
    raw_end = raw_start + len(attr_keys) - 1
    attr_columns = {key: raw_start + idx for idx, key in enumerate(attr_keys)}
    metadata_start = raw_start + len(attr_keys)
    data_start = header_row + 1
    data_end = data_start + len(records) - 1

    def coefficient_formula_for(weight_col: str, controls_row: int, signed_centered: bool) -> str:
        if signed_centered:
            return (
                f'=IF(MAX(ABS({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}),'
                f'ABS({ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row}))=0,0,'
                f'{ADVANCED_CONTROLS_SHEET_REF}!${weight_col}${controls_row}*100/'
                f'MAX(ABS({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}),'
                f'ABS({ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row})))'
            )
        return (
            f'=IF({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}={ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row},0,'
            f'{ADVANCED_CONTROLS_SHEET_REF}!${weight_col}${controls_row}*IF({ADVANCED_CONTROLS_SHEET_REF}!$K${controls_row}="Lower",-1,1)'
            f'*100/({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}-{ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row}))'
        )

    def offset_formula_for(weight_col: str, controls_row: int, signed_centered: bool) -> str:
        if signed_centered:
            return "0"
        return (
            f'=IF({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}={ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row},0,'
            f'{ADVANCED_CONTROLS_SHEET_REF}!${weight_col}${controls_row}*IF({ADVANCED_CONTROLS_SHEET_REF}!$K${controls_row}="Lower",'
            f'{ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row},-{ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row})'
            f'*100/({ADVANCED_CONTROLS_SHEET_REF}!$M${controls_row}-{ADVANCED_CONTROLS_SHEET_REF}!$L${controls_row}))'
        )

    for idx, key in enumerate(attr_keys):
        controls_row = WEIGHT_START_ROW + idx
        signed_centered = key in SIGNED_CENTERED_ATTRS
        coefficient_formula = coefficient_formula_for("C", controls_row, signed_centered)
        offset_formula = offset_formula_for("C", controls_row, signed_centered)
        fighting_coefficient_formula = coefficient_formula_for("E", controls_row, signed_centered)
        fighting_offset_formula = offset_formula_for("E", controls_row, signed_centered)
        fp_goods_coefficient_formula = coefficient_formula_for("G", controls_row, signed_centered)
        fp_goods_offset_formula = offset_formula_for("G", controls_row, signed_centered)
        qi_coefficient_formula = coefficient_formula_for("I", controls_row, signed_centered)
        qi_offset_formula = offset_formula_for("I", controls_row, signed_centered)
        sheet.cell(coefficient_row, raw_start + idx, coefficient_formula)
        sheet.cell(offset_row, raw_start + idx, offset_formula)
        sheet.cell(fighting_coefficient_row, raw_start + idx, fighting_coefficient_formula)
        sheet.cell(fighting_offset_row, raw_start + idx, fighting_offset_formula)
        sheet.cell(fp_goods_coefficient_row, raw_start + idx, fp_goods_coefficient_formula)
        sheet.cell(fp_goods_offset_row, raw_start + idx, fp_goods_offset_formula)
        sheet.cell(qi_coefficient_row, raw_start + idx, qi_coefficient_formula)
        sheet.cell(qi_offset_row, raw_start + idx, qi_offset_formula)

    overall_weights = overall_weight_map(attr_keys)
    records.sort(
        key=lambda record: (
            -default_score(record, attr_keys, stats, lambda key: overall_weights.get(key, 0.0)),
            str(record["name"]),
        )
    )
    for row_idx, record in enumerate(records, start=data_start):
        entity_id = str(record["entity_id"])
        values = [
            record["name"],
            None,
            None,
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['size_col'], age_data_context['max_row'], '\"\"')}"
                if age_data_context
                else record["size"]
            ),
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['road_col'], age_data_context['max_row'], '\"\"')}"
                if age_data_context
                else require_road_connection_label(record)
            ),
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['area_col'], age_data_context['max_row'], '0')}"
                if age_data_context
                else (numeric_cell(record["area"]) if record["area"] is not None else "")
            ),
        ]
        for col_idx, value in enumerate(values, start=1):
            sheet.cell(row_idx, col_idx, value)
        for attr_idx, key in enumerate(attr_keys):
            raw_value = float(record["attrs"].get(key, 0.0))
            if age_data_context:
                raw_formula = age_data_lookup_formula(
                    entity_id,
                    age_data_context["attr_columns"][key],
                    age_data_context["max_row"],
                    "0",
                )
                raw_expr = raw_formula
            else:
                raw_expr = cached_number(raw_value)
            cell = sheet.cell(row_idx, raw_start + attr_idx)
            if key == PROD_FP_ATTR and BOOST_FP_ATTR in attr_columns:
                boost_cell = f"{get_column_letter(attr_columns[BOOST_FP_ATTR])}{row_idx}"
                cell.value = f"={raw_expr}+{boost_cell}*{CONTROLS_SHEET_REF}!{ESTIMATED_FP_PRODUCTION_CELL}/100"
            elif key == PROD_GOODS_ATTR and (
                BOOST_GOODS_ATTR in attr_columns or BOOST_SPECIAL_GOODS_ATTR in attr_columns
            ):
                boost_terms = []
                if BOOST_GOODS_ATTR in attr_columns:
                    boost_terms.append(
                        f"{get_column_letter(attr_columns[BOOST_GOODS_ATTR])}{row_idx}"
                        f"*{CONTROLS_SHEET_REF}!{ESTIMATED_GOODS_PRODUCTION_CELL}/100"
                    )
                if BOOST_SPECIAL_GOODS_ATTR in attr_columns:
                    boost_terms.append(
                        f"{get_column_letter(attr_columns[BOOST_SPECIAL_GOODS_ATTR])}{row_idx}"
                        f"*{CONTROLS_SHEET_REF}!{ESTIMATED_SPECIAL_GOODS_PRODUCTION_CELL}/100"
                    )
                boost_expr = "+".join(boost_terms)
                cell.value = f"={raw_expr}+{boost_expr}"
            elif key == PROD_GUILD_GOODS_ATTR and BOOST_GUILD_GOODS_ATTR in attr_columns:
                boost_cell = f"{get_column_letter(attr_columns[BOOST_GUILD_GOODS_ATTR])}{row_idx}"
                cell.value = f"={raw_expr}+{boost_cell}*{CONTROLS_SHEET_REF}!{ESTIMATED_GUILD_GOODS_PRODUCTION_CELL}/100"
            elif key == PROD_MEDALS_ATTR and BOOST_MEDALS_ATTR in attr_columns:
                boost_cell = f"{get_column_letter(attr_columns[BOOST_MEDALS_ATTR])}{row_idx}"
                cell.value = f"={raw_expr}+{boost_cell}*{CONTROLS_SHEET_REF}!{ESTIMATED_MEDAL_PRODUCTION_CELL}/100"
            elif age_data_context:
                cell.value = f"={raw_expr}"
            else:
                cell.value = numeric_cell(raw_value)

        metadata_values = [
            record["type"],
            f"={CONTROLS_SHEET_REF}!{CITY_AGE_CELL}" if age_data_context else record["selected_age"],
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['available_col'], age_data_context['max_row'], '\"\"')}"
                if age_data_context
                else record["available"]
            ),
            building_category_label(str(record["entity_id"])),
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['environment_col'], age_data_context['max_row'], '\"\"')}"
                if age_data_context
                else record["environment_effect"]
            ),
            record["entity_id"],
            (
                f"={age_data_lookup_formula(entity_id, age_data_context['reward_col'], age_data_context['max_row'], '\"\"')}"
                if age_data_context
                else record["reward_production"]
            ),
        ]
        for col_idx, value in enumerate(metadata_values, start=metadata_start):
            sheet.cell(row_idx, col_idx, value)

        if attr_keys:
            raw_range = f"{get_column_letter(raw_start)}{row_idx}:{get_column_letter(raw_end)}{row_idx}"
            coefficient_range = f"${get_column_letter(raw_start)}${coefficient_row}:${get_column_letter(raw_end)}${coefficient_row}"
            offset_range = f"${get_column_letter(raw_start)}${offset_row}:${get_column_letter(raw_end)}${offset_row}"
            category_cell = f"{get_column_letter(metadata_start + 3)}{row_idx}"
            score_formula = (
                f"IF({ADVANCED_CONTROLS_SHEET_REF}!{OVERALL_TOTAL_WEIGHT_CELL}=0,0,"
                f"(SUMPRODUCT({raw_range},{coefficient_range})+SUM({offset_range}))/{ADVANCED_CONTROLS_SHEET_REF}!{OVERALL_TOTAL_WEIGHT_CELL})"
            )
            sheet.cell(
                row_idx,
                3,
                f"=IF(OR({CONTROLS_SHEET_REF}!{BUILDING_CATEGORY_FILTER_CELL}={excel_string(ALL_BUILDING_CATEGORIES)},{category_cell}={CONTROLS_SHEET_REF}!{BUILDING_CATEGORY_FILTER_CELL}),{score_formula},\"\")",
            )
        else:
            sheet.cell(row_idx, 3, 0)
        sheet.cell(row_idx, 2, f'=IF(C{row_idx}="","",1+COUNTIF($C${data_start}:$C${data_end},">"&C{row_idx}))')

    for row in sheet.iter_rows(min_row=data_start, max_row=data_end, min_col=1, max_col=len(all_headers)):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == metadata_start + 6)
            if cell.column in (2, 3) or raw_start <= cell.column <= raw_end:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(all_headers))}{data_end}"
    sheet.row_dimensions[coefficient_row].hidden = True
    sheet.row_dimensions[offset_row].hidden = True
    sheet.row_dimensions[fighting_coefficient_row].hidden = True
    sheet.row_dimensions[fighting_offset_row].hidden = True
    sheet.row_dimensions[fp_goods_coefficient_row].hidden = True
    sheet.row_dimensions[fp_goods_offset_row].hidden = True
    sheet.row_dimensions[qi_coefficient_row].hidden = True
    sheet.row_dimensions[qi_offset_row].hidden = True

    widths = {
        "A": 34,
        "B": 10,
        "C": 12,
        "D": 10,
        "E": 20,
        "F": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    for col_idx in range(raw_start, raw_end + 1):
        column_letter = get_column_letter(col_idx)
        sheet.column_dimensions[column_letter].width = 18
        if is_road_connection_attr_key(attr_keys[col_idx - raw_start]):
            sheet.column_dimensions[column_letter].hidden = True
    metadata_widths = [18, 18, 17, 24, 48, 28, 92]
    for offset, width in enumerate(metadata_widths):
        sheet.column_dimensions[get_column_letter(metadata_start + offset)].width = width
    sheet.column_dimensions[get_column_letter(metadata_start)].hidden = True
    sheet.column_dimensions[get_column_letter(metadata_start + 2)].hidden = True
    sheet.column_dimensions[get_column_letter(metadata_start + 5)].hidden = True
    apply_building_name_color_rules(
        sheet,
        data_start,
        data_end,
        metadata_start + 5,
        event_reward_abbreviations(records),
    )

    if records:
        score_range = f"C{data_start}:C{data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )


def write_overall_ranking_view_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(OVERALL_RANKING_SHEET)
    sheet.sheet_view.showGridLines = False

    base_headers = [
        "Building",
        "Overall Rank",
        "Overall Score",
        "Size",
        REQUIRE_ROAD_HEADER,
        "Area",
    ]
    metadata_headers = [
        "Type",
        "Selected Age",
        "Available By Age",
        "Building Category",
        "Environment Effect",
        "Entity ID",
        "Fragment / Reward Production",
        "Source Row",
    ]
    display_attr_keys = overall_ranking_display_attr_keys(attr_keys)
    raw_headers = [overall_ranking_attr_label(key) for key in display_attr_keys]
    all_headers = base_headers + raw_headers + metadata_headers

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    row_count = min(OVERALL_TOP_N, len(records))
    sheet["A1"] = f"Top {row_count} Overall Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(all_headers))

    header_row = BUILDING_HEADER_ROW
    data_start = header_row + 1
    data_end = data_start + row_count - 1
    raw_start = len(base_headers) + 1
    raw_end = raw_start + len(display_attr_keys) - 1
    metadata_start = raw_start + len(display_attr_keys)
    source_metadata_start = RAW_START_COLUMN + len(attr_keys)
    source_row_col = metadata_start + len(metadata_headers) - 1
    source_row_cell_col = get_column_letter(source_row_col)

    for col_idx, header in enumerate(all_headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    score_range = f"'{OVERALL_SCORE_SHEET}'!$B${score_data_start}:$B${score_data_end}"
    match_range = f"'{OVERALL_SCORE_SHEET}'!$H${score_data_start}:$H${score_data_end}"
    source_row_range = f"'{OVERALL_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"
    source_mapping = {
        1: "A",
        4: "D",
        5: "E",
        6: "F",
        metadata_start: get_column_letter(source_metadata_start),
        metadata_start + 1: get_column_letter(source_metadata_start + 1),
        metadata_start + 2: get_column_letter(source_metadata_start + 2),
        metadata_start + 3: get_column_letter(source_metadata_start + 3),
        metadata_start + 4: get_column_letter(source_metadata_start + 4),
        metadata_start + 5: get_column_letter(source_metadata_start + 5),
        metadata_start + 6: get_column_letter(source_metadata_start + 6),
    }

    for row_idx in range(data_start, data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"{source_row_cell_col}{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE(FILTER({score_range},{match_range}=1),{relative_rank}),"")')
        sheet.cell(
            row_idx,
            source_row_col,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},({score_range}={score_cell})*({match_range}=1)),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            if output_col == metadata_start + 6:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell})&"")')
            else:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(display_attr_keys, start=raw_start):
            if key == NET_HAPPINESS_ATTR:
                gross_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness"))
                demand_expr = "0"
                if "happiness_demanded" in attr_keys:
                    demand_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness_demanded"))
                    demand_expr = f"INDEX('{OVERALL_SOURCE_SHEET}'!${demand_col}:${demand_col},${source_row_cell})"
                sheet.cell(
                    row_idx,
                    attr_idx,
                    f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${gross_col}:${gross_col},${source_row_cell})+{demand_expr})',
                )
            else:
                source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
                sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    for row in sheet.iter_rows(min_row=data_start, max_row=data_end, min_col=1, max_col=len(all_headers)):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == metadata_start + 6)
            if cell.column in (2, 3, 6) or raw_start <= cell.column <= raw_end:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(all_headers))}{data_end}"
    for row_idx in range(2, header_row):
        sheet.row_dimensions[row_idx].hidden = True
    widths = {
        "A": 34,
        "B": 10,
        "C": 12,
        "D": 10,
        "E": 20,
        "F": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    for col_idx in range(raw_start, raw_end + 1):
        column_letter = get_column_letter(col_idx)
        sheet.column_dimensions[column_letter].width = 18
        if is_road_connection_attr_key(display_attr_keys[col_idx - raw_start]):
            sheet.column_dimensions[column_letter].hidden = True
    metadata_widths = [18, 18, 17, 24, 48, 28, 92, 10]
    for offset, width in enumerate(metadata_widths):
        sheet.column_dimensions[get_column_letter(metadata_start + offset)].width = width
    sheet.column_dimensions[get_column_letter(metadata_start)].hidden = True
    sheet.column_dimensions[get_column_letter(metadata_start + 2)].hidden = True
    sheet.column_dimensions[get_column_letter(metadata_start + 5)].hidden = True
    sheet.column_dimensions[get_column_letter(source_row_col)].hidden = True
    apply_building_name_color_rules(
        sheet,
        data_start,
        data_end,
        metadata_start + 5,
        event_reward_abbreviations(records),
    )

    if records:
        sheet.conditional_formatting.add(
            f"C{data_start}:C{data_end}",
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )


def write_overall_scores_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(OVERALL_SCORE_SHEET)
    sheet.sheet_state = "hidden"

    headers = [
        "Source Row",
        "Overall Score",
        "Overall Score Rank",
        "Adjusted Area",
        "Overall Efficiency Score",
        "Overall Efficiency Rank",
        "Building Category",
        "Category Match",
    ]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_start = 2
    data_end = data_start + len(records) - 1
    raw_start = RAW_START_COLUMN
    raw_end = raw_start + len(attr_keys) - 1
    all_buildings_raw_start = get_column_letter(raw_start)
    all_buildings_raw_end = get_column_letter(raw_end)
    score_range = f"$B${data_start}:$B${data_end}"
    efficiency_score_range = f"$E${data_start}:$E${data_end}"
    match_range = f"$H${data_start}:$H${data_end}"
    for idx, record in enumerate(records):
        row_idx = data_start + idx
        source_row = BUILDING_DATA_START_ROW + idx
        sheet.cell(row_idx, 1, source_row)
        if attr_keys:
            raw_range = f"'{OVERALL_SOURCE_SHEET}'!{all_buildings_raw_start}{source_row}:{all_buildings_raw_end}{source_row}"
            coefficient_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$2:${all_buildings_raw_end}$2"
            offset_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$3:${all_buildings_raw_end}$3"
            sheet.cell(
                row_idx,
                2,
                f"=IF({ADVANCED_CONTROLS_SHEET_REF}!{OVERALL_TOTAL_WEIGHT_CELL}=0,0,(SUMPRODUCT({raw_range},{coefficient_range})+SUM({offset_range}))/{ADVANCED_CONTROLS_SHEET_REF}!{OVERALL_TOTAL_WEIGHT_CELL})",
            )
        else:
            sheet.cell(row_idx, 2, 0)
        sheet.cell(row_idx, 3, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({score_range}>B{row_idx})*({match_range}=1)))')
        area_formula = f"'{OVERALL_SOURCE_SHEET}'!$F${source_row}+IF('{OVERALL_SOURCE_SHEET}'!$E${source_row}=\"Y\",1,0)"
        sheet.cell(row_idx, 4, f"={area_formula}")
        sheet.cell(row_idx, 5, f"=IF(D{row_idx}=0,0,B{row_idx}/D{row_idx})")
        sheet.cell(row_idx, 6, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({efficiency_score_range}>E{row_idx})*({match_range}=1)))')
        sheet.cell(row_idx, 7, building_category_label(str(record["entity_id"])))
        sheet.cell(row_idx, 8, building_category_match_formula(f"G{row_idx}"))

    for col_idx in range(1, 9):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 16


def write_fighting_scores_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(FIGHTING_SCORE_SHEET)
    sheet.sheet_state = "hidden"

    headers = [
        "Source Row",
        "Fighting Score",
        "Fighting Score Rank",
        "Adjusted Area",
        "Fighting Efficiency Score",
        "Fighting Efficiency Rank",
        "Building Category",
        "Category Match",
    ]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_start = 2
    data_end = data_start + len(records) - 1
    raw_start = RAW_START_COLUMN
    raw_end = raw_start + len(attr_keys) - 1
    all_buildings_raw_start = get_column_letter(raw_start)
    all_buildings_raw_end = get_column_letter(raw_end)
    score_range = f"$B${data_start}:$B${data_end}"
    efficiency_score_range = f"$E${data_start}:$E${data_end}"
    match_range = f"$H${data_start}:$H${data_end}"
    for idx, record in enumerate(records):
        row_idx = data_start + idx
        source_row = BUILDING_DATA_START_ROW + idx
        sheet.cell(row_idx, 1, source_row)
        if attr_keys:
            raw_range = f"'{OVERALL_SOURCE_SHEET}'!{all_buildings_raw_start}{source_row}:{all_buildings_raw_end}{source_row}"
            coefficient_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$4:${all_buildings_raw_end}$4"
            offset_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$5:${all_buildings_raw_end}$5"
            sheet.cell(
                row_idx,
                2,
                f"=IF({ADVANCED_CONTROLS_SHEET_REF}!{FIGHTING_TOTAL_WEIGHT_CELL}=0,0,(SUMPRODUCT({raw_range},{coefficient_range})+SUM({offset_range}))/{ADVANCED_CONTROLS_SHEET_REF}!{FIGHTING_TOTAL_WEIGHT_CELL})",
            )
        else:
            sheet.cell(row_idx, 2, 0)
        sheet.cell(row_idx, 3, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({score_range}>B{row_idx})*({match_range}=1)))')
        area_formula = f"'{OVERALL_SOURCE_SHEET}'!$F${source_row}+IF('{OVERALL_SOURCE_SHEET}'!$E${source_row}=\"Y\",1,0)"
        sheet.cell(row_idx, 4, f"={area_formula}")
        sheet.cell(row_idx, 5, f"=IF(D{row_idx}=0,0,B{row_idx}/D{row_idx})")
        sheet.cell(row_idx, 6, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({efficiency_score_range}>E{row_idx})*({match_range}=1)))')
        sheet.cell(row_idx, 7, building_category_label(str(record["entity_id"])))
        sheet.cell(row_idx, 8, building_category_match_formula(f"G{row_idx}"))

    for col_idx in range(1, 9):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 16


def write_fighting_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet("Fighting Ranking")
    sheet.sheet_view.showGridLines = False

    fighting_attr_keys = [key for key in attr_keys if fighting_weight_for_attr(key)]
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "Fighting Rank",
        "Fighting Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in fighting_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} Fighting Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "Uses the Fighting Weight controls. Non-fighting attributes default to zero in that control set."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    data_end_all = BUILDING_DATA_START_ROW + len(records) - 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    fighting_score_range = f"'{FIGHTING_SCORE_SHEET}'!$B${score_data_start}:$B${score_data_end}"
    fighting_source_row_range = f"'{FIGHTING_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        4: "D",
        5: "E",
        6: "F",
        7: "G",
        8: "H",
        9: "J",
        10: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"K{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({fighting_score_range},{relative_rank}),"")')
        sheet.cell(
            row_idx,
            11,
            f'=IF({score_cell}="","",INDEX(FILTER({fighting_source_row_range},{fighting_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(fighting_attr_keys, start=12):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (9,))
            if cell.column in (2, 3, 8) or cell.column >= 12:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 14,
        "D": 18,
        "E": 18,
        "F": 17,
        "G": 10,
        "H": 10,
        "I": 92,
        "J": 28,
        "K": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["K"].hidden = True
    for col_idx in range(12, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def write_fighting_efficiency_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(FIGHTING_EFFICIENCY_SHEET)
    sheet.sheet_view.showGridLines = False

    fighting_attr_keys = [key for key in attr_keys if fighting_weight_for_attr(key)]
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "Efficiency Rank",
        "Fighting Efficiency Score",
        "Fighting Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Adjusted Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in fighting_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} Fighting Efficiency Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "Fighting efficiency is Fighting Score divided by adjusted area. Adjusted area adds 1 when the building requires a road connection."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    efficiency_score_range = f"'{FIGHTING_SCORE_SHEET}'!$E${score_data_start}:$E${score_data_end}"
    fighting_source_row_range = f"'{FIGHTING_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        5: "D",
        6: "E",
        7: "F",
        8: "G",
        9: "H",
        11: "J",
        12: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"M{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({efficiency_score_range},{relative_rank}),"")')
        sheet.cell(row_idx, 4, f'=IF(${source_row_cell}="","",INDEX(\'{FIGHTING_SCORE_SHEET}\'!$B:$B,MATCH(${source_row_cell},\'{FIGHTING_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(row_idx, 10, f'=IF(${source_row_cell}="","",INDEX(\'{FIGHTING_SCORE_SHEET}\'!$D:$D,MATCH(${source_row_cell},\'{FIGHTING_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(
            row_idx,
            13,
            f'=IF({score_cell}="","",INDEX(FILTER({fighting_source_row_range},{efficiency_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(fighting_attr_keys, start=14):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (11,))
            if cell.column in (2, 3, 4, 9, 10) or cell.column >= 14:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 18,
        "D": 14,
        "E": 18,
        "F": 18,
        "G": 17,
        "H": 10,
        "I": 10,
        "J": 13,
        "K": 92,
        "L": 28,
        "M": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["M"].hidden = True
    for col_idx in range(14, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def fp_goods_display_attr_keys(attr_keys: Sequence[str]) -> List[str]:
    preferred = [
        PROD_FP_ATTR,
        PROD_GOODS_ATTR,
        PROD_MEDALS_ATTR,
        NET_HAPPINESS_ATTR,
        "prod_resource_blueprint",
        "prod_resource_premium",
        "prod_resource_supplies",
        "prod_resource_all_goods_of_previous_age",
        "prod_resource_all_goods_of_age",
        "prod_resource_all_goods_of_next_age",
        "prod_resource_special_goods_up_to_age",
        PROD_GUILD_GOODS_ATTR,
        BOOST_FP_ATTR,
        BOOST_GOODS_ATTR,
        BOOST_SPECIAL_GOODS_ATTR,
    ]
    out = [key for key in preferred if key in attr_keys]
    for key in attr_keys:
        label = attr_label(key)
        if key not in out and (
            fp_goods_weight_for_attr(key)
            or label in {"Production: FPs", "Production: Goods Total", "Production: Guild Goods"}
            or "Goods" in label
        ):
            out.append(key)
    return out


def qi_display_attr_keys(attr_keys: Sequence[str]) -> List[str]:
    return [key for key in attr_keys if is_qi_attr(key)]


def street_connection_column(attr_keys: Sequence[str]) -> Optional[str]:
    for key in attr_keys:
        if is_road_connection_attr_key(key):
            return get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
    return None


def write_ranked_score_sheet(
    workbook: Workbook,
    sheet_name: str,
    score_sheet_name: str,
    rank_header: str,
    score_header: str,
    title: str,
    note: str,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
    display_attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(sheet_name)
    sheet.sheet_view.showGridLines = False
    display_attr_keys = [key for key in display_attr_keys if not is_road_connection_attr_key(key)]

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    attr_start = 7
    metadata_start = attr_start + len(display_attr_keys)
    type_col = metadata_start
    selected_age_col = metadata_start + 1
    available_col = metadata_start + 2
    entity_col = metadata_start + 3
    source_row_col = metadata_start + 4
    fragment_col = metadata_start + 5
    all_buildings_metadata_start = RAW_START_COLUMN + len(attr_keys)
    headers = (
        ["Building", rank_header, score_header, "Size", REQUIRE_ROAD_HEADER, "Area"]
        + [attr_label(key) for key in display_attr_keys]
        + [
            "Type",
            "Selected Age",
            "Available By Age",
            "Entity ID",
            "Source Row",
            "Fragment / Reward Production",
        ]
    )

    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = note
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    score_range = f"'{score_sheet_name}'!$B${score_data_start}:$B${score_data_end}"
    match_range = f"'{score_sheet_name}'!$H${score_data_start}:$H${score_data_end}"
    source_row_range = f"'{score_sheet_name}'!$A${score_data_start}:$A${score_data_end}"
    source_row_cell_col = get_column_letter(source_row_col)

    source_mapping = {
        1: "A",
        4: "D",
        5: "E",
        6: "F",
        type_col: get_column_letter(all_buildings_metadata_start),
        selected_age_col: get_column_letter(all_buildings_metadata_start + 1),
        available_col: get_column_letter(all_buildings_metadata_start + 2),
        entity_col: get_column_letter(all_buildings_metadata_start + 5),
        fragment_col: get_column_letter(all_buildings_metadata_start + 6),
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"{source_row_cell_col}{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE(FILTER({score_range},{match_range}=1),{relative_rank}),"")')
        sheet.cell(
            row_idx,
            source_row_col,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},({score_range}={score_cell})*({match_range}=1)),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            if output_col == fragment_col:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell})&"")')
            else:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(display_attr_keys, start=attr_start):
            if key == NET_HAPPINESS_ATTR:
                gross_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness"))
                demand_expr = "0"
                if "happiness_demanded" in attr_keys:
                    demand_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness_demanded"))
                    demand_expr = f"INDEX('{OVERALL_SOURCE_SHEET}'!${demand_col}:${demand_col},${source_row_cell})"
                sheet.cell(
                    row_idx,
                    attr_idx,
                    f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${gross_col}:${gross_col},${source_row_cell})+{demand_expr})',
                )
            else:
                source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
                sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == fragment_col)
            if cell.column in (2, 3, 6) or attr_start <= cell.column < metadata_start:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_data_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_data_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        1: 34,
        2: 12,
        3: 14,
        4: 10,
        5: 20,
        6: 10,
        type_col: 18,
        selected_age_col: 18,
        available_col: 17,
        entity_col: 28,
        source_row_col: 10,
        fragment_col: 92,
    }
    for col_idx, width in widths.items():
        sheet.column_dimensions[get_column_letter(col_idx)].width = width
    sheet.column_dimensions[source_row_cell_col].hidden = True
    sheet.column_dimensions[get_column_letter(type_col)].hidden = True
    sheet.column_dimensions[get_column_letter(available_col)].hidden = True
    sheet.column_dimensions[get_column_letter(entity_col)].hidden = True
    for col_idx in range(attr_start, metadata_start):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18
    apply_building_name_color_rules(
        sheet,
        data_start,
        output_data_end,
        entity_col,
        event_reward_abbreviations(records),
    )


def write_ranked_efficiency_sheet(
    workbook: Workbook,
    sheet_name: str,
    score_sheet_name: str,
    efficiency_score_header: str,
    base_score_header: str,
    title: str,
    note: str,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
    display_attr_keys: Sequence[str],
    top_n: int = FIGHTING_TOP_N,
    attr_label_func: Callable[[str], str] = attr_label,
) -> None:
    sheet = workbook.create_sheet(sheet_name)
    sheet.sheet_view.showGridLines = False
    display_attr_keys = [key for key in display_attr_keys if not is_road_connection_attr_key(key)]

    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    attr_start = 9
    metadata_start = attr_start + len(display_attr_keys)
    type_col = metadata_start
    selected_age_col = metadata_start + 1
    available_col = metadata_start + 2
    entity_col = metadata_start + 3
    source_row_col = metadata_start + 4
    fragment_col = metadata_start + 5
    all_buildings_metadata_start = RAW_START_COLUMN + len(attr_keys)
    headers = (
        [
            "Building",
            "Efficiency Rank",
            efficiency_score_header,
            base_score_header,
            "Size",
            REQUIRE_ROAD_HEADER,
            "Area",
            "Adjusted Area",
        ]
        + [attr_label_func(key) for key in display_attr_keys]
        + [
            "Type",
            "Selected Age",
            "Available By Age",
            "Entity ID",
            "Source Row",
            "Fragment / Reward Production",
        ]
    )

    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = note
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(top_n, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    efficiency_score_range = f"'{score_sheet_name}'!$E${score_data_start}:$E${score_data_end}"
    match_range = f"'{score_sheet_name}'!$H${score_data_start}:$H${score_data_end}"
    source_row_range = f"'{score_sheet_name}'!$A${score_data_start}:$A${score_data_end}"
    source_row_cell_col = get_column_letter(source_row_col)

    source_mapping = {
        1: "A",
        5: "D",
        6: "E",
        7: "F",
        type_col: get_column_letter(all_buildings_metadata_start),
        selected_age_col: get_column_letter(all_buildings_metadata_start + 1),
        available_col: get_column_letter(all_buildings_metadata_start + 2),
        entity_col: get_column_letter(all_buildings_metadata_start + 5),
        fragment_col: get_column_letter(all_buildings_metadata_start + 6),
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"{source_row_cell_col}{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE(FILTER({efficiency_score_range},{match_range}=1),{relative_rank}),"")')
        sheet.cell(row_idx, 4, f'=IF(${source_row_cell}="","",INDEX(\'{score_sheet_name}\'!$B:$B,MATCH(${source_row_cell},\'{score_sheet_name}\'!$A:$A,0)))')
        sheet.cell(row_idx, 8, f'=IF(${source_row_cell}="","",INDEX(\'{score_sheet_name}\'!$D:$D,MATCH(${source_row_cell},\'{score_sheet_name}\'!$A:$A,0)))')
        sheet.cell(
            row_idx,
            source_row_col,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},({efficiency_score_range}={score_cell})*({match_range}=1)),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            if output_col == fragment_col:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell})&"")')
            else:
                sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(display_attr_keys, start=attr_start):
            if key == NET_HAPPINESS_ATTR:
                gross_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness"))
                demand_expr = "0"
                if "happiness_demanded" in attr_keys:
                    demand_col = get_column_letter(RAW_START_COLUMN + attr_keys.index("happiness_demanded"))
                    demand_expr = f"INDEX('{OVERALL_SOURCE_SHEET}'!${demand_col}:${demand_col},${source_row_cell})"
                sheet.cell(
                    row_idx,
                    attr_idx,
                    f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${gross_col}:${gross_col},${source_row_cell})+{demand_expr})',
                )
            else:
                source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
                sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == fragment_col)
            if cell.column in (2, 3, 4, 7, 8) or attr_start <= cell.column < metadata_start:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_data_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_data_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        1: 34,
        2: 12,
        3: 18,
        4: 14,
        5: 10,
        6: 20,
        7: 10,
        8: 13,
        type_col: 18,
        selected_age_col: 18,
        available_col: 17,
        entity_col: 28,
        source_row_col: 10,
        fragment_col: 92,
    }
    for col_idx, width in widths.items():
        sheet.column_dimensions[get_column_letter(col_idx)].width = width
    sheet.column_dimensions[source_row_cell_col].hidden = True
    sheet.column_dimensions[get_column_letter(type_col)].hidden = True
    sheet.column_dimensions[get_column_letter(available_col)].hidden = True
    sheet.column_dimensions[get_column_letter(entity_col)].hidden = True
    for col_idx in range(attr_start, metadata_start):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18
    apply_building_name_color_rules(
        sheet,
        data_start,
        output_data_end,
        entity_col,
        event_reward_abbreviations(records),
    )


def write_fp_goods_scores_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(FP_GOODS_SCORE_SHEET)
    sheet.sheet_state = "hidden"

    headers = [
        "Source Row",
        "Farming Score",
        "Farming Score Rank",
        "Adjusted Area",
        "Farming Efficiency Score",
        "Farming Efficiency Rank",
        "Building Category",
        "Category Match",
    ]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_start = 2
    data_end = data_start + len(records) - 1
    raw_start = RAW_START_COLUMN
    raw_end = raw_start + len(attr_keys) - 1
    all_buildings_raw_start = get_column_letter(raw_start)
    all_buildings_raw_end = get_column_letter(raw_end)
    score_range = f"$B${data_start}:$B${data_end}"
    efficiency_score_range = f"$E${data_start}:$E${data_end}"
    match_range = f"$H${data_start}:$H${data_end}"
    for idx, record in enumerate(records):
        row_idx = data_start + idx
        source_row = BUILDING_DATA_START_ROW + idx
        sheet.cell(row_idx, 1, source_row)
        if attr_keys:
            raw_range = f"'{OVERALL_SOURCE_SHEET}'!{all_buildings_raw_start}{source_row}:{all_buildings_raw_end}{source_row}"
            coefficient_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$6:${all_buildings_raw_end}$6"
            offset_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$7:${all_buildings_raw_end}$7"
            sheet.cell(
                row_idx,
                2,
                f"=IF({ADVANCED_CONTROLS_SHEET_REF}!{FP_GOODS_TOTAL_WEIGHT_CELL}=0,0,(SUMPRODUCT({raw_range},{coefficient_range})+SUM({offset_range}))/{ADVANCED_CONTROLS_SHEET_REF}!{FP_GOODS_TOTAL_WEIGHT_CELL})",
            )
        else:
            sheet.cell(row_idx, 2, 0)
        sheet.cell(row_idx, 3, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({score_range}>B{row_idx})*({match_range}=1)))')
        area_formula = f"'{OVERALL_SOURCE_SHEET}'!$F${source_row}+IF('{OVERALL_SOURCE_SHEET}'!$E${source_row}=\"Y\",1,0)"
        sheet.cell(row_idx, 4, f"={area_formula}")
        sheet.cell(row_idx, 5, f"=IF(D{row_idx}=0,0,B{row_idx}/D{row_idx})")
        sheet.cell(row_idx, 6, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({efficiency_score_range}>E{row_idx})*({match_range}=1)))')
        sheet.cell(row_idx, 7, building_category_label(str(record["entity_id"])))
        sheet.cell(row_idx, 8, building_category_match_formula(f"G{row_idx}"))

    for col_idx in range(1, 9):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 16


def write_fp_goods_ranking_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(FP_GOODS_PRODUCTION_SHEET)
    sheet.sheet_view.showGridLines = False

    production_attr_keys = fp_goods_display_attr_keys(attr_keys)
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "Farming Rank",
        "Farming Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in production_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} Farming Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "Uses the Farming Weight controls. Default primary weight is split between FPs and Goods Total; secondary weight covers medals, net happiness, blueprints, diamonds, and supplies."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    fp_goods_score_range = f"'{FP_GOODS_SCORE_SHEET}'!$B${score_data_start}:$B${score_data_end}"
    source_row_range = f"'{FP_GOODS_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        4: "D",
        5: "E",
        6: "F",
        7: "G",
        8: "H",
        9: "J",
        10: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"K{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({fp_goods_score_range},{relative_rank}),"")')
        sheet.cell(
            row_idx,
            11,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},{fp_goods_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(production_attr_keys, start=12):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (9,))
            if cell.column in (2, 3, 8) or cell.column >= 12:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 14,
        "D": 18,
        "E": 18,
        "F": 17,
        "G": 10,
        "H": 10,
        "I": 92,
        "J": 28,
        "K": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["K"].hidden = True
    for col_idx in range(12, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def write_fp_goods_efficiency_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(FP_GOODS_EFFICIENCY_SHEET)
    sheet.sheet_view.showGridLines = False

    production_attr_keys = fp_goods_display_attr_keys(attr_keys)
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "Efficiency Rank",
        "Farming Efficiency Score",
        "Farming Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Adjusted Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in production_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} Farming Efficiency Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "Farming efficiency is Farming Score divided by adjusted area. Default farming weight includes FPs, Goods Total, medals, net happiness, blueprints, diamonds, and supplies."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    efficiency_score_range = f"'{FP_GOODS_SCORE_SHEET}'!$E${score_data_start}:$E${score_data_end}"
    source_row_range = f"'{FP_GOODS_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        5: "D",
        6: "E",
        7: "F",
        8: "G",
        9: "H",
        11: "J",
        12: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"M{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({efficiency_score_range},{relative_rank}),"")')
        sheet.cell(row_idx, 4, f'=IF(${source_row_cell}="","",INDEX(\'{FP_GOODS_SCORE_SHEET}\'!$B:$B,MATCH(${source_row_cell},\'{FP_GOODS_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(row_idx, 10, f'=IF(${source_row_cell}="","",INDEX(\'{FP_GOODS_SCORE_SHEET}\'!$D:$D,MATCH(${source_row_cell},\'{FP_GOODS_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(
            row_idx,
            13,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},{efficiency_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(production_attr_keys, start=14):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (11,))
            if cell.column in (2, 3, 4, 9, 10) or cell.column >= 14:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 18,
        "D": 14,
        "E": 18,
        "F": 18,
        "G": 17,
        "H": 10,
        "I": 10,
        "J": 13,
        "K": 92,
        "L": 28,
        "M": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["M"].hidden = True
    for col_idx in range(14, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def write_qi_scores_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(QI_SCORE_SHEET)
    sheet.sheet_state = "hidden"

    headers = [
        "Source Row",
        "QI Score",
        "QI Score Rank",
        "Adjusted Area",
        "QI Efficiency Score",
        "QI Efficiency Rank",
        "Building Category",
        "Category Match",
    ]
    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(1, col_idx, header)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_start = 2
    data_end = data_start + len(records) - 1
    raw_start = RAW_START_COLUMN
    raw_end = raw_start + len(attr_keys) - 1
    all_buildings_raw_start = get_column_letter(raw_start)
    all_buildings_raw_end = get_column_letter(raw_end)
    score_range = f"$B${data_start}:$B${data_end}"
    efficiency_score_range = f"$E${data_start}:$E${data_end}"
    match_range = f"$H${data_start}:$H${data_end}"
    for idx, record in enumerate(records):
        row_idx = data_start + idx
        source_row = BUILDING_DATA_START_ROW + idx
        sheet.cell(row_idx, 1, source_row)
        if attr_keys:
            raw_range = f"'{OVERALL_SOURCE_SHEET}'!{all_buildings_raw_start}{source_row}:{all_buildings_raw_end}{source_row}"
            coefficient_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$8:${all_buildings_raw_end}$8"
            offset_range = f"'{OVERALL_SOURCE_SHEET}'!${all_buildings_raw_start}$9:${all_buildings_raw_end}$9"
            sheet.cell(
                row_idx,
                2,
                f"=IF({ADVANCED_CONTROLS_SHEET_REF}!{QI_TOTAL_WEIGHT_CELL}=0,0,(SUMPRODUCT({raw_range},{coefficient_range})+SUM({offset_range}))/{ADVANCED_CONTROLS_SHEET_REF}!{QI_TOTAL_WEIGHT_CELL})",
            )
        else:
            sheet.cell(row_idx, 2, 0)
        sheet.cell(row_idx, 3, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({score_range}>B{row_idx})*({match_range}=1)))')
        area_formula = f"'{OVERALL_SOURCE_SHEET}'!$F${source_row}+IF('{OVERALL_SOURCE_SHEET}'!$E${source_row}=\"Y\",1,0)"
        sheet.cell(row_idx, 4, f"={area_formula}")
        sheet.cell(row_idx, 5, f"=IF(D{row_idx}=0,0,B{row_idx}/D{row_idx})")
        sheet.cell(row_idx, 6, f'=IF(H{row_idx}=0,"",1+SUMPRODUCT(({efficiency_score_range}>E{row_idx})*({match_range}=1)))')
        sheet.cell(row_idx, 7, building_category_label(str(record["entity_id"])))
        sheet.cell(row_idx, 8, building_category_match_formula(f"G{row_idx}"))

    for col_idx in range(1, 9):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 16


def write_qi_ranking_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(QI_RANKING_SHEET)
    sheet.sheet_view.showGridLines = False

    qi_attr_keys = qi_display_attr_keys(attr_keys)
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "QI Rank",
        "QI Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in qi_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} QI Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "Uses the QI Weight controls. Includes attributes whose data key or label is QI-related."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    qi_score_range = f"'{QI_SCORE_SHEET}'!$B${score_data_start}:$B${score_data_end}"
    source_row_range = f"'{QI_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        4: "D",
        5: "E",
        6: "F",
        7: "G",
        8: "H",
        9: "J",
        10: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"K{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({qi_score_range},{relative_rank}),"")')
        sheet.cell(
            row_idx,
            11,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},{qi_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(qi_attr_keys, start=12):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (9,))
            if cell.column in (2, 3, 8) or cell.column >= 12:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 14,
        "D": 18,
        "E": 18,
        "F": 17,
        "G": 10,
        "H": 10,
        "I": 92,
        "J": 28,
        "K": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["K"].hidden = True
    for col_idx in range(12, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def write_qi_efficiency_sheet(
    workbook: Workbook,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
) -> None:
    sheet = workbook.create_sheet(QI_EFFICIENCY_SHEET)
    sheet.sheet_view.showGridLines = False

    qi_attr_keys = qi_display_attr_keys(attr_keys)
    title_fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL_COLOR)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Building",
        "Efficiency Rank",
        "QI Efficiency Score",
        "QI Score",
        "Type",
        "Selected Age",
        "Available By Age",
        "Size",
        "Area",
        "Adjusted Area",
        "Fragment / Reward Production",
        "Entity ID",
        "Source Row",
    ] + [attr_label(key) for key in qi_attr_keys]

    sheet["A1"] = f"Top {min(FIGHTING_TOP_N, len(records))} QI Efficiency Buildings"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = title_fill
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet["A2"] = "QI efficiency is QI Score divided by adjusted area. Adjusted area adds 1 when the building requires a road connection."
    sheet["A2"].alignment = Alignment(wrap_text=False)

    header_row = 4
    data_start = header_row + 1
    row_count = min(FIGHTING_TOP_N, len(records))
    output_data_end = data_start + row_count - 1

    for col_idx, header in enumerate(headers, start=1):
        cell = sheet.cell(header_row, col_idx, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    score_data_start = 2
    score_data_end = score_data_start + len(records) - 1
    efficiency_score_range = f"'{QI_SCORE_SHEET}'!$E${score_data_start}:$E${score_data_end}"
    source_row_range = f"'{QI_SCORE_SHEET}'!$A${score_data_start}:$A${score_data_end}"

    source_mapping = {
        1: "A",
        5: "D",
        6: "E",
        7: "F",
        8: "G",
        9: "H",
        11: "J",
        12: "K",
    }

    for row_idx in range(data_start, output_data_end + 1):
        relative_rank = row_idx - data_start + 1
        score_cell = f"C{row_idx}"
        source_row_cell = f"M{row_idx}"
        sheet.cell(row_idx, 2, f'=IF({score_cell}="","",ROWS($B${data_start}:B{row_idx}))')
        sheet.cell(row_idx, 3, f'=IFERROR(LARGE({efficiency_score_range},{relative_rank}),"")')
        sheet.cell(row_idx, 4, f'=IF(${source_row_cell}="","",INDEX(\'{QI_SCORE_SHEET}\'!$B:$B,MATCH(${source_row_cell},\'{QI_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(row_idx, 10, f'=IF(${source_row_cell}="","",INDEX(\'{QI_SCORE_SHEET}\'!$D:$D,MATCH(${source_row_cell},\'{QI_SCORE_SHEET}\'!$A:$A,0)))')
        sheet.cell(
            row_idx,
            13,
            f'=IF({score_cell}="","",INDEX(FILTER({source_row_range},{efficiency_score_range}={score_cell}),COUNTIF($C${data_start}:{score_cell},{score_cell})))',
        )
        for output_col, source_col in source_mapping.items():
            sheet.cell(row_idx, output_col, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')
        for attr_idx, key in enumerate(qi_attr_keys, start=14):
            source_col = get_column_letter(RAW_START_COLUMN + attr_keys.index(key))
            sheet.cell(row_idx, attr_idx, f'=IF(${source_row_cell}="","",INDEX(\'{OVERALL_SOURCE_SHEET}\'!${source_col}:${source_col},${source_row_cell}))')

    max_col = len(headers)
    for row in sheet.iter_rows(min_row=data_start, max_row=max(output_data_end, header_row), min_col=1, max_col=max_col):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (11,))
            if cell.column in (2, 3, 4, 9, 10) or cell.column >= 14:
                cell.number_format = "0.00"

    sheet.freeze_panes = f"B{header_row + 1}"
    if row_count:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max_col)}{output_data_end}"
        score_range = f"C{data_start}:C{output_data_end}"
        sheet.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="min",
                start_color="F8696B",
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color="63BE7B",
            ),
        )

    widths = {
        "A": 34,
        "B": 12,
        "C": 18,
        "D": 14,
        "E": 18,
        "F": 18,
        "G": 17,
        "H": 10,
        "I": 10,
        "J": 13,
        "K": 92,
        "L": 28,
        "M": 10,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.column_dimensions["M"].hidden = True
    for col_idx in range(14, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def write_about_sheet(
    workbook: Workbook,
    reference_file: str,
    era: str,
    records: Sequence[Dict[str, Any]],
    attr_keys: Sequence[str],
    available_only: bool,
    all_ages: bool = False,
) -> None:
    sheet = workbook.create_sheet("About")
    sheet.sheet_view.showGridLines = False
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    sheet["A1"] = "Workbook Guide"
    sheet["A1"].font = Font(bold=True, size=15, color=TITLE_FONT_COLOR)
    sheet["A1"].fill = PatternFill("solid", fgColor=TITLE_FILL_COLOR)
    sheet["A1"].border = border
    sheet.merge_cells("A1:B1")
    notes = [
        ("Reference file", display_path(reference_file)),
        ("Default selected age" if all_ages else "Assumed age", selected_age_display(era, all_ages)),
        ("Version", WORKBOOK_VERSION),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Buildings included", len(records)),
        ("Attributes discovered", len(attr_keys)),
        ("Available only filter", "Yes" if available_only else "No"),
        ("Estimated base FP production default", format_amount(DEFAULT_ESTIMATED_FP_PRODUCTION)),
        ("Estimated base regular goods production default", format_amount(DEFAULT_ESTIMATED_GOODS_PRODUCTION)),
        ("Estimated base special goods production default", format_amount(DEFAULT_ESTIMATED_SPECIAL_GOODS_PRODUCTION)),
        ("Estimated base guild goods production default", format_amount(DEFAULT_ESTIMATED_GUILD_GOODS_PRODUCTION)),
        ("Estimated base medal production default", format_amount(DEFAULT_ESTIMATED_MEDAL_PRODUCTION)),
        ("Start here", "Use Main Controls first. Pick your city age, enter your city's estimated base production for FP, regular goods, special goods, guild goods, and medals without percentage-based boosts, then choose the fighting, QI, and Production FP/Goods focus settings that match your priorities." if all_ages else "Use Main Controls first. Enter your city's estimated base production for FP, regular goods, special goods, guild goods, and medals without percentage-based boosts, then choose the fighting, QI, and Production FP/Goods focus settings that match your priorities."),
        ("All-age mode", "The selected city age on Main Controls updates the age-sensitive source values used by the ranking and efficiency sheets." if all_ages else "This workbook was generated for one fixed assumed age."),
        ("Scale controls", "Each 1-5 scale works left to right: 1 fully favors the left option, 3 is balanced, and 5 fully favors the right option."),
        ("Fighting focus", "Main Controls lets you tune GBG vs GE, red vs blue army use, attack vs defense boosts, and current-age vs next-age unit production."),
        ("Production FP/Goods focus", f"Main Controls cell {PRODUCTION_FP_GOODS_FOCUS_CELL.replace('$', '')} tunes FP vs goods production value. Default 2 is FP-heavy; 3 is balanced. The setting affects both Overall Ranking and Farming ranking weights."),
        ("QI role", "Choose whether QI fighting value should favor blue, red, or both roles."),
        ("Advanced controls", "Use Advanced Controls only for fine tuning. Leave Weight mode as Default to restore generated weights, or switch to Custom and enter yellow override values in the right-side override columns. A higher override weight makes that attribute matter more; zero turns it off."),
        ("Building source category filter", "Use the Main Controls source category dropdown to show all buildings or only a color-coded reward/event category on the ranking sheets."),
        ("Production boost conversion", "Boost percentages use matching Main Controls estimates: regular goods boost uses regular goods production, special goods boost uses special goods production, guild goods boost uses guild goods production, and FP/medal boosts use their own totals."),
        ("Base coin and supplies production", "Base Production: Coin and Base Production: Supplies on the Overall Ranking and Overall Efficiency Ranking sheets do not include percentage-based boosts."),
        ("Goods total", "Regular goods rollup: named goods, all/random goods of previous/current/next age, special goods up to age, and era_goods. It excludes FP, medals, money, supplies, guild goods, and settlement resources."),
        ("Guild goods", "Guild goods are tracked separately from regular goods, so changing one estimate does not change the other."),
        ("Happiness", "Gross Happiness shows happiness provided by the building. Net Happiness subtracts internal happiness demand; demand is still tracked as a negative scoring input but is not shown as a separate ranking column."),
        ("Overall ranking", f"Use {OVERALL_RANKING_SHEET} for a broad building comparison across production, fighting, and other weighted attributes. Overall fighting uses fixed sub-budgets for all non-QI combat, GBG, GE, QI, and unit production, and those sub-budgets follow the Main Controls fighting focus and QI fighter role settings."),
        ("Production normalization", "Major production scores are anchored to the Main Controls production assumptions so one extreme building does not define the full scoring range by itself."),
        ("Footprint", "Overall Ranking does not directly score footprint. Overall Efficiency divides Overall Score by adjusted area, adding one tile when a road connection is required."),
        ("Efficiency rankings", "Efficiency sheets favor buildings that score well for their footprint. Buildings that require a road connection are treated as needing one extra tile."),
        ("Fighting ranking", "Fighting Ranking uses your fighting focus settings and shows the top 100 fighting buildings."),
        ("Farming ranking", FARMING_RANKING_ABOUT_NOTE),
        ("QI ranking", "QI Ranking focuses on QI-related boosts, starting resources, action points, and the selected QI fighter role."),
        ("Building name colors", "Building names are color-coded by Entity ID: GBG rewards use W_MultiAge_GBG, QI rewards use W_MultiAge_GR, GE rewards use W_MultiAge_Expedition or W_MultiAge_GEX, and current-year event rewards use W_MultiAge_<event abbreviation><two-digit year><letter>... . Each workbook build scans the input data for current-year event abbreviations; newly detected events get an unused color, and assigned event colors stay fixed for the rest of that year."),
        ("Data scope", "Uses CityEntities reference definitions only; no placed-city quantities are used. Great buildings, QI settlement entities, and native era buildings are intentionally excluded from this reward-building workbook."),
    ]
    for row_idx, (label, value) in enumerate(notes, start=2):
        sheet.cell(row_idx, 1, label)
        sheet.cell(row_idx, 2, value)
        sheet.cell(row_idx, 1).font = Font(bold=True)
        sheet.cell(row_idx, 1).border = border
        sheet.cell(row_idx, 2).border = border
        sheet.cell(row_idx, 1).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.cell(row_idx, 2).alignment = Alignment(wrap_text=True, vertical="top")
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 100


def apply_sheet_tab_colors(workbook: Workbook) -> None:
    for sheet in workbook.worksheets:
        color = TAB_COLORS.get(sheet.title)
        if color:
            sheet.sheet_properties.tabColor = color


def build_workbook(reference_file: str, era: str, output_file: str, available_only: bool, all_ages: bool = False) -> None:
    payload = load_payload(reference_file)
    entities = payload.get("CityEntities")
    if not isinstance(entities, dict):
        raise SystemExit(f"CityEntities not found in reference file: {reference_file}")

    age_data_context: Optional[Dict[str, Any]] = None
    records_by_age: Dict[str, List[Dict[str, Any]]] = {}
    if all_ages:
        records_by_age, attr_keys = build_age_records(entities, list(AGE_ORDER), available_only)
        records = list(records_by_age.get(era, []))
        seen_entity_ids = {str(record["entity_id"]) for record in records}
        for age_records in records_by_age.values():
            for record in age_records:
                entity_id = str(record["entity_id"])
                if entity_id not in seen_entity_ids:
                    records.append(record)
                    seen_entity_ids.add(entity_id)
    else:
        records, attr_keys = collect_records(entities, era, available_only)
    stats = compute_attribute_stats(records, attr_keys)
    category_options = building_category_options(records)

    workbook = Workbook()
    workbook.calculation.calcMode = "auto"
    workbook.calculation.calcOnSave = True
    workbook.calculation.calcCompleted = False
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    write_controls_sheet(workbook, reference_file, era, available_only, all_ages, category_options)
    write_advanced_controls_sheet(workbook, reference_file, era, attr_keys, stats, available_only, len(records), all_ages)
    write_category_options_sheet(workbook, category_options)
    write_goods_resource_audit_sheet(workbook, attr_keys)
    if all_ages:
        write_age_options_sheet(workbook)
        age_data_context = write_age_data_sheet(workbook, records_by_age, attr_keys)
    write_buildings_sheet(workbook, records, attr_keys, stats, age_data_context)
    write_overall_scores_sheet(workbook, records, attr_keys)
    write_overall_ranking_view_sheet(workbook, records, attr_keys)
    write_ranked_efficiency_sheet(
        workbook,
        OVERALL_EFFICIENCY_SHEET,
        OVERALL_SCORE_SHEET,
        "Overall Efficiency Score",
        "Overall Score",
        f"Top {min(OVERALL_TOP_N, len(records))} Overall Efficiency Buildings",
        "Overall efficiency is Overall Score divided by adjusted area. Adjusted area adds 1 when the building requires a road connection.",
        records,
        attr_keys,
        overall_ranking_display_attr_keys(attr_keys),
        top_n=OVERALL_TOP_N,
        attr_label_func=overall_ranking_attr_label,
    )
    write_fighting_scores_sheet(workbook, records, attr_keys)
    write_ranked_score_sheet(
        workbook,
        "Fighting Ranking",
        FIGHTING_SCORE_SHEET,
        "Fighting Rank",
        "Fighting Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} Fighting Buildings",
        "Uses the Fighting Weight controls. Non-fighting attributes default to zero in that control set.",
        records,
        attr_keys,
        [key for key in attr_keys if fighting_weight_for_attr(key)],
    )
    write_ranked_efficiency_sheet(
        workbook,
        FIGHTING_EFFICIENCY_SHEET,
        FIGHTING_SCORE_SHEET,
        "Fighting Efficiency Score",
        "Fighting Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} Fighting Efficiency Buildings",
        "Fighting efficiency is Fighting Score divided by adjusted area. Adjusted area adds 1 when the building requires a road connection.",
        records,
        attr_keys,
        [key for key in attr_keys if fighting_weight_for_attr(key)],
    )
    write_fp_goods_scores_sheet(workbook, records, attr_keys)
    write_ranked_score_sheet(
        workbook,
        FP_GOODS_PRODUCTION_SHEET,
        FP_GOODS_SCORE_SHEET,
        "Farming Rank",
        "Farming Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} Farming Buildings",
        "Uses the Farming Weight controls. Default primary weight is split between FPs and Goods Total; secondary weight covers medals, net happiness, blueprints, diamonds, and supplies.",
        records,
        attr_keys,
        fp_goods_display_attr_keys(attr_keys),
    )
    write_ranked_efficiency_sheet(
        workbook,
        FP_GOODS_EFFICIENCY_SHEET,
        FP_GOODS_SCORE_SHEET,
        "Farming Efficiency Score",
        "Farming Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} Farming Efficiency Buildings",
        "Farming efficiency is Farming Score divided by adjusted area. Default farming weight includes FPs, Goods Total, medals, net happiness, blueprints, diamonds, and supplies.",
        records,
        attr_keys,
        fp_goods_display_attr_keys(attr_keys),
    )
    write_qi_scores_sheet(workbook, records, attr_keys)
    write_ranked_score_sheet(
        workbook,
        QI_RANKING_SHEET,
        QI_SCORE_SHEET,
        "QI Rank",
        "QI Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} QI Buildings",
        "Uses the QI Weight controls. Includes attributes whose data key or label is QI-related.",
        records,
        attr_keys,
        qi_display_attr_keys(attr_keys),
    )
    write_ranked_efficiency_sheet(
        workbook,
        QI_EFFICIENCY_SHEET,
        QI_SCORE_SHEET,
        "QI Efficiency Score",
        "QI Score",
        f"Top {min(FIGHTING_TOP_N, len(records))} QI Efficiency Buildings",
        "QI efficiency is QI Score divided by adjusted area. Adjusted area adds 1 when the building requires a road connection.",
        records,
        attr_keys,
        qi_display_attr_keys(attr_keys),
    )
    write_about_sheet(workbook, reference_file, era, records, attr_keys, available_only, all_ages)
    apply_sheet_tab_colors(workbook)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    workbook.save(output_file)
    populate_formula_caches(output_file, records, attr_keys, stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help="Reference JSON file containing CityEntities. Defaults to input/ref/zpwd-ref.",
    )
    parser.add_argument(
        "--era",
        default="VirtualFuture",
        choices=list(AGE_ORDER),
        help="Assumed user age used for age-specific building attributes.",
    )
    parser.add_argument(
        "--available-only",
        action="store_true",
        help="Only include buildings whose native era is at or before the selected age.",
    )
    parser.add_argument(
        "--all_ages",
        "--all-ages",
        dest="all_ages",
        action="store_true",
        help="Build an all-age workbook with a Main Controls dropdown for the selected city age.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output .xlsx path. Defaults to output/building_attribute_ranking_<reference>_<era>.xlsx, "
            "or output/Interactive_Building_Rankings-All_Ages.xlsx in all-age mode."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reference_file = os.path.abspath(args.reference)
    output_file = args.output
    if not output_file:
        if args.all_ages:
            output_file = os.path.join(OUTPUT_DIR, "Interactive_Building_Rankings-All_Ages.xlsx")
        else:
            token = safe_output_token(reference_file)
            output_file = os.path.join(OUTPUT_DIR, f"building_attribute_ranking_{token}_{args.era}.xlsx")
    build_workbook(reference_file, args.era, os.path.abspath(output_file), args.available_only, args.all_ages)
    print(f"Wrote {display_path(output_file)}")


if __name__ == "__main__":
    main()
