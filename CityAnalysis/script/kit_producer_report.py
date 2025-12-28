#!/usr/bin/env python3
"""List buildings that produce One Up/Renovation kits or fragments in a given era."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from glob import glob
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

BASE_DIR = os.path.expanduser("~/Documents/FOE/CityAnalysis")
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TARGET_KIT_SUBTYPES = {"one_up_kit": "One Up Kit", "renovation_kit": "Renovation Kit"}


def latest_city_file() -> str:
    files = glob(os.path.join(INPUT_DIR, "city_*.json"))
    if not files:
        raise SystemExit(f"No city JSON files found in {INPUT_DIR}")
    return max(files, key=os.path.getmtime)


def parse_reward_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    subtype = entry.get("subType")
    assembled = entry.get("assembledReward")
    if subtype == "fragment" and isinstance(assembled, dict):
        kit_sub = assembled.get("subType")
        if kit_sub in TARGET_KIT_SUBTYPES:
            return {
                "kit_subtype": kit_sub,
                "kit_label": TARGET_KIT_SUBTYPES[kit_sub],
                "amount": entry.get("amount", 0),
                "unit": "fragments",
                "name": entry.get("name", f"Fragments of {TARGET_KIT_SUBTYPES[kit_sub]}")
            }
    elif subtype in TARGET_KIT_SUBTYPES:
        return {
            "kit_subtype": subtype,
            "kit_label": TARGET_KIT_SUBTYPES[subtype],
            "amount": entry.get("amount", 0),
            "unit": "kits",
            "name": entry.get("name", TARGET_KIT_SUBTYPES[subtype])
        }

    if isinstance(assembled, dict) and assembled.get("subType") in TARGET_KIT_SUBTYPES:
        kit_sub = assembled["subType"]
        return {
            "kit_subtype": kit_sub,
            "kit_label": TARGET_KIT_SUBTYPES[kit_sub],
            "amount": entry.get("amount", 0),
            "unit": entry.get("subType", "items"),
            "name": entry.get("name", TARGET_KIT_SUBTYPES[kit_sub])
        }
    return None


def reward_lookup(component: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup = component.get("lookup")
    if not isinstance(lookup, dict):
        return {}
    rewards = lookup.get("rewards")
    if isinstance(rewards, dict):
        return rewards
    if isinstance(rewards, list):  # sometimes stored as a flat list
        out: Dict[str, Dict[str, Any]] = {}
        for entry in rewards:
            if isinstance(entry, dict):
                rid = entry.get("id")
                if isinstance(rid, str):
                    out[rid] = entry
        return out
    return {}


DROP_KEYS = ("dropChance", "drop_chance", "chance", "probability")


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
) -> Iterable[Tuple[str, Dict[str, Any], Optional[str], Optional[int], Optional[float], bool]]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="List kit-producing buildings for a specific era")
    parser.add_argument("--era", default="VirtualFuture", help="Era to inspect (default: VirtualFuture)")
    args = parser.parse_args()

    if not os.path.isdir(INPUT_DIR):
        raise SystemExit(f"Input directory not found: {INPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    latest_file = latest_city_file()
    with open(latest_file, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    entities = data.get("CityEntities")
    if not isinstance(entities, dict):
        raise SystemExit("CityEntities not found in JSON")

    matches: List[Dict[str, Any]] = []
    for entity in entities.values():
        if not isinstance(entity, dict):
            continue
        components = entity.get("components")
        if not isinstance(components, dict):
            continue
        era_component = components.get(args.era)
        if not isinstance(era_component, dict):
            continue

        lookup = reward_lookup(era_component)
        era_rewards: List[Dict[str, Any]] = []
        for reward_id, fallback, option_name, option_time, drop_chance, requires_motivation in iter_reward_products(era_component):
            reward_entry = lookup.get(reward_id, fallback)
            parsed = parse_reward_entry(reward_entry)
            if not parsed:
                continue
            parsed["option_name"] = option_name
            parsed["option_time"] = option_time
            parsed["reward_id"] = reward_id or reward_entry.get("id")
            parsed["drop_chance"] = drop_chance
            parsed["requires_motivation"] = requires_motivation
            era_rewards.append(parsed)

        if not era_rewards:
            continue

        matches.append(
            {
                "id": entity.get("id"),
                "name": entity.get("name", entity.get("id")),
                "size": extract_size(entity),
                "street": extract_street_requirement(entity, era_component),
                "rewards": era_rewards,
            }
        )

    kit_reports = aggregate_kit_reports(matches)
    if not any(kit_reports.values()):
        print(f"No kit-producing buildings found for era {args.era} in {os.path.basename(latest_file)}")
        return

    safe_era = args.era.replace(" ", "_")
    output_paths = {}
    for kit_key, buildings in kit_reports.items():
        label = TARGET_KIT_SUBTYPES[kit_key]
        filename = f"{kit_key}_buildings_{safe_era}.txt"
        output_path = os.path.join(OUTPUT_DIR, filename)
        output_paths[kit_key] = output_path
        write_report(output_path, latest_file, args.era, label, buildings)

    excel_path = os.path.join(OUTPUT_DIR, f"kit_buildings_{safe_era}.xlsx")
    write_excel_report(excel_path, latest_file, args.era, kit_reports)

    print(f"Latest file: {latest_file}")
    print(f"Era inspected: {args.era}")
    for kit_key in TARGET_KIT_SUBTYPES:
        report = kit_reports.get(kit_key, [])
        count = len(report)
        print(
            f"{TARGET_KIT_SUBTYPES[kit_key]}: {count} building(s) written to {output_paths.get(kit_key)}"
        )
    print(f"Excel workbook: {excel_path}")


def aggregate_kit_reports(matches: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    kit_map: Dict[str, Dict[str, Any]] = {key: {} for key in TARGET_KIT_SUBTYPES}

    for entry in matches:
        size = entry.get("size")
        area = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"
        street = entry.get("street")
        building_id = entry.get("id") or entry.get("name")
        for reward in entry["rewards"]:
            kit_key = reward.get("kit_subtype")
            if kit_key not in kit_map:
                continue

            amount = float(reward.get("amount", 0) or 0)
            unit = reward.get("unit", "items")
            fragments = amount
            source_note = ""
            if unit == "kits":
                fragments *= 30
                plural = "s" if not math.isclose(amount, 1.0) else ""
                source_note = f" ({format_number(amount)} kit{plural})"
            elif unit != "fragments":
                source_note = f" ({format_number(amount)} {unit})"

            drop_prob = reward.get("drop_chance")
            prob = drop_prob if isinstance(drop_prob, (int, float)) else None
            effective_prob = prob if isinstance(prob, (int, float)) else 1.0
            expected_fragments = fragments * effective_prob

            time_label = format_time_label(reward.get("option_time"))
            needs_motivation = bool(reward.get("requires_motivation"))

            bucket = kit_map[kit_key].setdefault(
                building_id,
                {
                    "name": entry.get("name", building_id),
                    "size_label": size_label,
                    "area": area,
                    "street": street,
                    "records": [],
                    "expected": 0.0,
                },
            )
            bucket["expected"] += expected_fragments
            bucket["records"].append(
                {
                    "fragments": fragments,
                    "source_note": source_note,
                    "time_label": time_label,
                    "probability": prob,
                    "needs_motivation": needs_motivation,
                }
            )

    sorted_reports: Dict[str, List[Dict[str, Any]]] = {}
    for kit_key, buildings in kit_map.items():
        ranked: List[Dict[str, Any]] = []
        for data in buildings.values():
            area = data.get("area")
            efficiency = data["expected"] / area if area else 0.0
            data["efficiency"] = efficiency
            ranked.append(data)
        ranked.sort(key=lambda entry: (-entry["efficiency"], entry["name"]))
        sorted_reports[kit_key] = ranked
    return sorted_reports


def format_time_label(time_seconds: Optional[int]) -> str:
    if not isinstance(time_seconds, int):
        return ""
    if time_seconds % 3600 == 0:
        hours = time_seconds // 3600
        return f"{hours}h"
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


def write_report(
    path: str,
    source_file: str,
    era: str,
    kit_label: str,
    buildings: List[Dict[str, Any]],
) -> None:
    lines: List[str] = []
    lines.append(f"Source file: {source_file}")
    lines.append(f"Era: {era}")
    lines.append(f"Kit type: {kit_label}")
    lines.append(f"Total buildings: {len(buildings)}")
    lines.append("")

    for idx, info in enumerate(buildings, start=1):
        street = info.get("street")
        street_label = str(street) if street is not None else "n/a"
        efficiency = info.get("efficiency", 0.0)
        efficiency_label = (
            f"{efficiency:.3f}"
            if info.get("area")
            else "n/a"
        )
        expected = info.get("expected", 0.0)
        lines.append(
            f"{idx}. {info['name']} | size {info['size_label']} | street {street_label} | efficiency {efficiency_label} fragments/tile"
        )
        lines.append(
            f"   Expected fragments per cycle: {format_number(expected)}"
        )
        for record in info.get("records", []):
            chance_label = format_probability(record.get("probability"))
            chance_suffix = f" @ {chance_label} chance" if chance_label else ""
            motivation_suffix = " (needs motivation)" if record.get("needs_motivation") else ""
            time_label = record.get("time_label")
            time_suffix = f" ({time_label})" if time_label else ""
            lines.append(
                f"   - {format_number(record['fragments'])} fragments{record['source_note']}{time_suffix}{chance_suffix}{motivation_suffix}"
            )
        lines.append("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def write_excel_report(
    path: str,
    source_file: str,
    era: str,
    kit_reports: Dict[str, List[Dict[str, Any]]],
) -> None:
    sheet_specs = []
    for kit_key, kit_label in TARGET_KIT_SUBTYPES.items():
        buildings = kit_reports.get(kit_key, [])
        rows = build_sheet_rows(buildings)
        sheet_specs.append((kit_label, rows))
    create_xlsx(path, sheet_specs, era, source_file)


def build_sheet_rows(buildings: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    rows: List[List[Dict[str, Any]]] = []
    rows.append(
        [
            cell("Rank"),
            cell("Building"),
            cell("Size"),
            cell("Street Requirement"),
            cell("Efficiency (fragments/tile)"),
            cell("Expected fragments/cycle"),
            cell("Details"),
        ]
    )

    for idx, info in enumerate(buildings, start=1):
        street = info.get("street")
        street_cell = (
            cell(street, "number") if isinstance(street, (int, float)) else cell("n/a")
        )

        efficiency = info.get("efficiency") if info.get("area") else None
        efficiency_cell = (
            cell(round(efficiency, 6), "number") if isinstance(efficiency, (int, float)) else cell("n/a")
        )

        expected = info.get("expected", 0.0)
        expected_cell = cell(round(expected, 6), "number")

        detail_lines: List[str] = []
        for record in info.get("records", []):
            fragment_str = format_number(record["fragments"])
            detail = f"{fragment_str} fragments"
            if record.get("source_note"):
                detail += record["source_note"]
            if record.get("time_label"):
                detail += f" ({record['time_label']})"
            if record.get("probability") is not None:
                detail += f" @ {format_probability(record['probability'])}"
            if record.get("needs_motivation"):
                detail += " (needs motivation)"
            detail_lines.append(detail)
        details = "\n".join(detail_lines)

        rows.append(
            [
                cell(idx, "number"),
                cell(info.get("name")),
                cell(info.get("size_label")),
                street_cell,
                efficiency_cell,
                expected_cell,
                cell(details),
            ]
        )

    return rows


def cell(value: Any, cell_type: str = "string") -> Dict[str, Any]:
    return {"value": value, "type": cell_type}


def create_xlsx(
    path: str,
    sheets: List[Tuple[str, List[List[Dict[str, Any]]]]],
    era: str,
    source_file: str,
) -> None:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", build_content_types(len(sheets)))
        zf.writestr("_rels/.rels", build_root_rels())
        zf.writestr("docProps/core.xml", build_core_properties(timestamp))
        zf.writestr("docProps/app.xml", build_app_properties([name for name, _ in sheets]))
        zf.writestr("xl/styles.xml", build_styles_xml())
        zf.writestr("xl/workbook.xml", build_workbook_xml(sheets))
        zf.writestr("xl/_rels/workbook.xml.rels", build_workbook_rels(len(sheets)))

        for idx, (name, rows) in enumerate(sheets, start=1):
            sheet_xml = build_sheet_xml(rows)
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)


def build_content_types(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    ]
    for idx in range(1, sheet_count + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    overrides.extend(
        [
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
        ]
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(overrides)}"
        '</Types>'
    )
    return content


def build_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def build_core_properties(timestamp: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>CityAnalysis Script</dc:creator>'
        '<cp:lastModifiedBy>CityAnalysis Script</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        '</cp:coreProperties>'
    )


def build_app_properties(sheet_names: List[str]) -> str:
    heading_pairs = (
        '<HeadingPairs>'
        '<vt:vector size="2" baseType="variant">'
        '<vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
        f'<vt:variant><vt:i4>{len(sheet_names)}</vt:i4></vt:variant>'
        '</vt:vector>'
        '</HeadingPairs>'
    )
    titles = ''.join(f'<vt:lpstr>{escape(name)}</vt:lpstr>' for name in sheet_names)
    titles_block = f'<TitlesOfParts><vt:vector size="{len(sheet_names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>CityAnalysis Script</Application>'
        '<DocSecurity>0</DocSecurity>'
        '<ScaleCrop>false</ScaleCrop>'
        f'{heading_pairs}'
        f'{titles_block}'
        '<Company></Company>'
        '<LinksUpToDate>false</LinksUpToDate>'
        '<SharedDoc>false</SharedDoc>'
        '<HyperlinksChanged>false</HyperlinksChanged>'
        '<AppVersion>16.0300</AppVersion>'
        '</Properties>'
    )


def build_workbook_xml(sheets: List[Tuple[str, List[List[Dict[str, Any]]]]]) -> str:
    sheet_entries = []
    for idx, (name, _rows) in enumerate(sheets, start=1):
        safe_name = escape(name)
        sheet_entries.append(
            f'<sheet name="{safe_name}" sheetId="{idx}" r:id="rId{idx}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<fileVersion appName="xl"/>'
        '<sheets>'
        f"{''.join(sheet_entries)}"
        '</sheets>'
        '</workbook>'
    )


def build_workbook_rels(sheet_count: int) -> str:
    relationships = []
    for idx in range(1, sheet_count + 1):
        relationships.append(
            f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
        )
    relationships.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(relationships)}"
        '</Relationships>'
    )


def build_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def build_sheet_xml(rows: List[List[Dict[str, Any]]]) -> str:
    sheet_data = ['<sheetData>']
    for row_idx, row in enumerate(rows, start=1):
        sheet_data.append(f'<row r="{row_idx}">')
        for col_idx, cell_value in enumerate(row, start=1):
            ref = f"{column_name(col_idx)}{row_idx}"
            value = cell_value.get("value")
            ctype = cell_value.get("type", "string")
            if ctype == "number" and isinstance(value, (int, float)):
                sheet_data.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = "" if value is None else str(value)
                text = escape(text)
                text = text.replace("\n", "&#10;")
                sheet_data.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
                )
        sheet_data.append('</row>')
    sheet_data.append('</sheetData>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{''.join(sheet_data)}"
        '</worksheet>'
    )


def column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


if __name__ == "__main__":
    main()
