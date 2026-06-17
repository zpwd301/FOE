#!/usr/bin/env python3
"""Report buildings that produce guild goods for a given era."""
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
DROP_KEYS = ("dropChance", "drop_chance", "chance", "probability")


def latest_city_file() -> str:
    files = glob(os.path.join(INPUT_DIR, "city_*.json"))
    if not files:
        raise SystemExit(f"No city JSON files found in {INPUT_DIR}")
    return max(files, key=os.path.getmtime)


def normalize_probability(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        prob = float(value)
    elif isinstance(value, str):
        try:
            prob = float(value)
        except ValueError:
            return None
    else:
        return None
    if prob > 1:
        return prob / 100.0
    return prob


def iter_guild_products(
    component: Dict[str, Any]
) -> Iterable[Tuple[Dict[str, Any], Optional[str], Optional[int], Optional[float], bool]]:
    production = component.get("production")
    if not isinstance(production, dict):
        return []
    options = production.get("options")
    if not isinstance(options, list):
        return []

    def walk_product(
        product: Dict[str, Any],
        option_name: Optional[str],
        option_time: Optional[int],
        drop_chance: Optional[float],
        requires_motivation: bool,
    ) -> Iterable[Tuple[Dict[str, Any], Optional[str], Optional[int], Optional[float], bool]]:
        if not isinstance(product, dict):
            return []
        ptype = product.get("type")
        if ptype == "guildResources":
            yield product, option_name, option_time, drop_chance, requires_motivation
            return []
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
            return []
        if ptype == "chest":
            candidates = product.get("possible_rewards") or product.get("possibleRewards")
            if isinstance(candidates, list):
                for cand in candidates:
                    if not isinstance(cand, dict):
                        continue
                    reward = cand.get("reward")
                    if not isinstance(reward, dict):
                        continue
                    cand_drop = None
                    for key in DROP_KEYS:
                        if key in cand:
                            cand_drop = normalize_probability(cand.get(key))
                            break
                    yield from walk_product(
                        reward,
                        option_name,
                        option_time,
                        cand_drop if cand_drop is not None else drop_chance,
                        requires_motivation,
                    )
            return []
        return []

    for option in options:
        if not isinstance(option, dict):
            continue
        option_name = option.get("name")
        option_time = option.get("time")
        option_requires = bool(option.get("onlyWhenMotivated"))
        products = option.get("products")
        if not isinstance(products, list):
            continue
        for product in products:
            if not isinstance(product, dict):
                continue
            prod_drop = None
            for key in DROP_KEYS:
                if key in product:
                    prod_drop = normalize_probability(product.get(key))
                    break
            prod_requires = option_requires or bool(product.get("onlyWhenMotivated"))
            yield from walk_product(product, option_name, option_time, prod_drop, prod_requires)


GUILD_RESOURCE_KEYS = {
    "all_goods_of_age",
    "random_good_of_age",
    "random_goods_of_age",
    "random_good_of_previous_age",
    "random_good_of_next_age",
    "all_goods_of_previous_age",
    "all_goods_of_next_age",
}


def parse_guild_resource(product: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    guild = product.get("guildResources")
    if not isinstance(guild, dict):
        return None
    resources = guild.get("resources")
    if not isinstance(resources, dict):
        return None
    total = 0.0
    parts: List[str] = []
    for key, val in resources.items():
        if key not in GUILD_RESOURCE_KEYS:
            continue
        if isinstance(val, (int, float)):
            total += float(val)
            parts.append(f"{key}={val}")
    if total <= 0:
        return None
    breakdown = ", ".join(parts)
    return total, breakdown


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
            req_lvl = req_obj.get("requiredLevel")
            if isinstance(req_lvl, int):
                return req_lvl
            sc = req_obj.get("street_connection_level")
            if isinstance(sc, int):
                return sc
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


def cell(value: Any, cell_type: str = "string") -> Dict[str, Any]:
    return {"value": value, "type": cell_type}


def column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def build_sheet_rows(buildings: List[Dict[str, Any]], include_details: bool = True) -> List[List[Dict[str, Any]]]:
    rows: List[List[Dict[str, Any]]] = []
    rows.append(
        [
            cell("Rank"),
            cell("Building"),
            cell("Size"),
            cell("Street Requirement"),
            cell("Efficiency (goods/tile)"),
            cell("Expected goods/cycle"),
            cell("Details"),
        ]
    )
    for idx, info in enumerate(buildings, start=1):
        street = info.get("street")
        street_cell = cell(street, "number") if isinstance(street, (int, float)) else cell("n/a")
        efficiency = info.get("efficiency") if info.get("area") else None
        efficiency_cell = (
            cell(round(efficiency, 6), "number") if isinstance(efficiency, (int, float)) else cell("n/a")
        )
        expected = info.get("expected", 0.0)
        expected_cell = cell(round(expected, 6), "number")
        detail_lines: List[str] = []
        if include_details:
            for record in info.get("records", []):
                detail = f"{format_number(record['goods'])} goods"
                if record.get("breakdown"):
                    detail += f" ({record['breakdown']})"
                if record.get("time_label"):
                    detail += f" ({record['time_label']})"
                if record.get("probability") is not None:
                    detail += f" @ {format_probability(record['probability'])}"
                if record.get("needs_motivation"):
                    detail += " (needs motivation)"
                detail_lines.append(detail)
        else:
            for record in info.get("records", []):
                detail = f"{format_number(record['goods'])} goods"
                if record.get("probability") is not None:
                    detail += f" @ {format_probability(record['probability'])}"
                if record.get("needs_motivation"):
                    detail += " (needs motivation)"
                detail_lines.append(detail)
        rows.append(
            [
                cell(idx, "number"),
                cell(info.get("name")),
                cell(info.get("size_label")),
                street_cell,
                efficiency_cell,
                expected_cell,
                cell("\n".join(detail_lines)),
            ]
        )
    return rows


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
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(overrides)}"
        '</Types>'
    )


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


def build_workbook_xml(sheet_names: List[str]) -> str:
    sheet_entries = []
    for idx, name in enumerate(sheet_names, start=1):
        sheet_entries.append(f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
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
    for r_idx, row in enumerate(rows, start=1):
        sheet_data.append(f'<row r="{r_idx}">')
        for c_idx, cell_value in enumerate(row, start=1):
            ref = f"{column_name(c_idx)}{r_idx}"
            value = cell_value.get("value")
            ctype = cell_value.get("type", "string")
            if ctype == "number" and isinstance(value, (int, float)):
                sheet_data.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = "" if value is None else str(value)
                text = escape(text).replace("\n", "&#10;")
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


def write_excel_multi(path: str, sheet_specs: List[Tuple[str, List[List[Dict[str, Any]]]]]) -> None:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sheet_names = [name for name, _rows in sheet_specs]
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", build_content_types(len(sheet_specs)))
        zf.writestr("_rels/.rels", build_root_rels())
        zf.writestr("docProps/core.xml", build_core_properties(timestamp))
        zf.writestr("docProps/app.xml", build_app_properties(sheet_names))
        zf.writestr("xl/styles.xml", build_styles_xml())
        zf.writestr("xl/workbook.xml", build_workbook_xml(sheet_names))
        zf.writestr("xl/_rels/workbook.xml.rels", build_workbook_rels(len(sheet_specs)))
        for idx, (_name, rows) in enumerate(sheet_specs, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", build_sheet_xml(rows))


def aggregate_buildings(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buildings: List[Dict[str, Any]] = []
    for entry in matches:
        size = entry.get("size")
        area = None
        size_label = "unknown"
        if isinstance(size, tuple) and len(size) == 2 and all(isinstance(v, int) for v in size):
            area = size[0] * size[1]
            size_label = f"{size[0]}x{size[1]}"
        street = entry.get("street")
        name = entry.get("name") or entry.get("id")
        records = entry.get("records", [])
        expected = sum(record.get("expected", 0.0) for record in records)
        efficiency = expected / area if area else 0.0
        buildings.append(
            {
                "name": name,
                "size_label": size_label,
                "street": street,
                "records": records,
                "expected": expected,
                "efficiency": efficiency,
                "area": area,
            }
        )
    buildings.sort(key=lambda x: (-x["efficiency"], x["name"]))
    return buildings


def write_text_report(path: str, source_file: str, era: str, buildings: List[Dict[str, Any]]) -> None:
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
            f"{idx}. {info['name']} | size {info['size_label']} | street {street_label} | efficiency {efficiency_label} goods/tile"
        )
        lines.append(f"   Expected goods per cycle: {format_number(expected)}")
        for record in info.get("records", []):
            chance_label = format_probability(record.get("probability"))
            chance_suffix = f" @ {chance_label} chance" if chance_label else ""
            motivation_suffix = " (needs motivation)" if record.get("needs_motivation") else ""
            time_suffix = f" ({record['time_label']})" if record.get("time_label") else ""
            breakdown_suffix = f" ({record['breakdown']})" if record.get("breakdown") else ""
            lines.append(
                f"   - {format_number(record['goods'])} goods{breakdown_suffix}{time_suffix}{chance_suffix}{motivation_suffix}"
            )
        lines.append("")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def collect_era_components(components: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for era_name, comp in components.items():
        if era_name == "AllAge":
            continue
        if isinstance(comp, dict):
            yield era_name, comp


def main() -> None:
    parser = argparse.ArgumentParser(description="Report buildings that produce guild goods")
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

    era_matches: Dict[str, List[Dict[str, Any]]] = {}
    for entity in entities.values():
        if not isinstance(entity, dict):
            continue
        components = entity.get("components")
        if not isinstance(components, dict):
            continue
        for era_name, era_component in collect_era_components(components):
            records: List[Dict[str, Any]] = []
            for product, option_name, option_time, drop_chance, needs_motivation in iter_guild_products(era_component):
                parsed = parse_guild_resource(product)
                if not parsed:
                    continue
                goods_total, breakdown = parsed
                probability = drop_chance if isinstance(drop_chance, (int, float)) else None
                effective_prob = probability if isinstance(probability, (int, float)) else 1.0
                expected_goods = goods_total * effective_prob
                records.append(
                    {
                        "goods": goods_total,
                        "breakdown": breakdown,
                        "time_label": format_time_label(option_time),
                        "probability": probability,
                        "needs_motivation": needs_motivation,
                        "expected": expected_goods,
                    }
                )

            if not records:
                continue

            era_matches.setdefault(era_name, []).append(
                {
                    "id": entity.get("id"),
                    "name": entity.get("name", entity.get("id")),
                    "size": extract_size(entity),
                    "street": extract_street_requirement(entity, era_component),
                    "records": records,
                }
            )

    if not era_matches:
        print("No guild goods producers found in any era")
        return

    aggregated: Dict[str, List[Dict[str, Any]]] = {
        era: aggregate_buildings(matches) for era, matches in era_matches.items()
    }

    safe_era = args.era.replace(" ", "_")
    text_path = os.path.join(OUTPUT_DIR, f"guild_goods_buildings_{safe_era}.txt")
    excel_path = os.path.join(OUTPUT_DIR, f"guild_goods_{safe_era}.xlsx")

    target_buildings = aggregated.get(args.era)
    if target_buildings:
        write_text_report(text_path, latest_file, args.era, target_buildings)
    else:
        print(f"No guild goods producers found for era {args.era}; skipping text report")
        text_path = None

    sheet_rows = [("Guild Goods", build_sheet_rows(aggregated.get(args.era) or [], include_details=False))]
    write_excel_multi(excel_path, sheet_rows)

    print(f"Latest file: {latest_file}")
    print(f"Era inspected: {args.era}")
    if target_buildings:
        print(f"Total buildings: {len(target_buildings)} written to {text_path}")
    print(f"Excel workbook: {excel_path}")


if __name__ == "__main__":
    main()
