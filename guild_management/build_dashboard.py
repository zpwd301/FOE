#!/usr/bin/env python3
"""Build the static, multi-page GoE Guild Portal."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "site"
ASSET_SOURCE_DIR = SITE_DIR / "assets"
DEFAULT_DATA_SOURCE = SITE_DIR / "data" / "treasury-data.js"
DEFAULT_CONTRIBUTION_DATA_SOURCE = SITE_DIR / "data" / "contribution-data.js"
DEFAULT_OUTPUT_DIR = ROOT / "dashboard"
FINGERPRINT_LENGTH = 12
MINIMUM_FONT_SIZE_PX = 12
BANNER_WIDTHS = (720, 1200, 1956)
BANNER_FORMATS = ("avif", "webp", "jpg")
CONTRIBUTION_PERIODS = (("3", 3), ("7", 7), ("30", 30))
DEFAULT_CONTRIBUTION_PERIOD = "30"
CONTRIBUTION_DETAIL_RECORD_LIMIT = 500
CONTRIBUTION_ERA_LEADER_LIMIT = 3
ADMIN_CONTRIBUTION_PLAYER_ID = "855340115"
CACHEABLE_ASSET_SUFFIXES = frozenset(
    {".avif", ".css", ".gif", ".ico", ".jpeg", ".jpg", ".js", ".json", ".png", ".svg", ".webp", ".woff", ".woff2"}
)
FINGERPRINTED_ASSET_PATTERN = re.compile(
    rf"\.[0-9a-f]{{{FINGERPRINT_LENGTH}}}\.[^.]+$", re.IGNORECASE
)
TOKEN_PATTERN = re.compile(r"{{([a-z0-9_]+)}}")
HEADING_PATTERN = re.compile(
    r'<h(?P<level>[23])\s+id="(?P<anchor>[^"]+)"[^>]*>(?P<label>.*?)</h(?P=level)>',
    re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")
CSS_FONT_SIZE_PATTERNS = (
    re.compile(r"font-size\s*:\s*(?P<size>\d+(?:\.\d+)?)px", re.IGNORECASE),
    re.compile(r"font\s*:[^;{}]*?\b(?P<size>\d+(?:\.\d+)?)px", re.IGNORECASE),
)
SCRIPT_FONT_SIZE_PATTERNS = (
    re.compile(r'font-size\s*=\s*["\'](?P<size>\d+(?:\.\d+)?)(?:px)?["\']', re.IGNORECASE),
    re.compile(r'fontSize\s*[:=]\s*["\'](?P<size>\d+(?:\.\d+)?)px["\']'),
)


class PageInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[str] = []
        self.label_references: list[str] = []
        self.h1_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "h1":
            self.h1_count += 1
        for name in ("href", "src"):
            if values.get(name):
                self.references.append(str(values[name]))
        if values.get("srcset"):
            self.references.extend(
                candidate.strip().split()[0]
                for candidate in str(values["srcset"]).split(",")
                if candidate.strip()
            )
        if values.get("aria-labelledby"):
            self.label_references.extend(str(values["aria-labelledby"]).split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the GoE Guild Portal.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def render(template: str, values: dict[str, object]) -> str:
    def replacement(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"Missing template value: {key}")
        return str(values[key])

    rendered = TOKEN_PATTERN.sub(replacement, template)
    leftover = TOKEN_PATTERN.search(rendered)
    if leftover:
        raise ValueError(f"Unresolved template value: {leftover.group(1)}")
    return rendered


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def validate_minimum_font_size() -> None:
    """Reject published CSS or script-rendered labels below the accessibility floor."""
    errors: list[str] = []
    assets = (
        (ASSET_SOURCE_DIR / "styles.css", CSS_FONT_SIZE_PATTERNS),
        (ASSET_SOURCE_DIR / "app.js", SCRIPT_FONT_SIZE_PATTERNS),
    )
    for path, patterns in assets:
        if not path.is_file():
            continue
        for line_number, line in enumerate(read_text(path).splitlines(), start=1):
            for pattern in patterns:
                for match in pattern.finditer(line):
                    size = float(match.group("size"))
                    if size < MINIMUM_FONT_SIZE_PX:
                        errors.append(f"{path}:{line_number}: {size:g}px")
    if errors:
        raise ValueError(
            f"Minimum font size is {MINIMUM_FONT_SIZE_PX}px; found smaller values:\n"
            + "\n".join(errors)
        )


def validate_output(output_dir: Path) -> None:
    pages: dict[Path, PageInspector] = {}
    errors: list[str] = []
    for page_path in sorted(output_dir.rglob("*.html")):
        inspector = PageInspector()
        inspector.feed(read_text(page_path))
        pages[page_path] = inspector
        duplicate_ids = sorted({item for item in inspector.ids if inspector.ids.count(item) > 1})
        if duplicate_ids:
            errors.append(f"{page_path}: duplicate ids: {', '.join(duplicate_ids)}")
        if inspector.h1_count != 1:
            errors.append(f"{page_path}: expected one h1, found {inspector.h1_count}")
        missing_labels = sorted(set(inspector.label_references) - set(inspector.ids))
        if missing_labels:
            errors.append(f"{page_path}: missing aria-labelledby ids: {', '.join(missing_labels)}")

    for page_path, inspector in pages.items():
        for reference in inspector.references:
            parsed = urlsplit(reference)
            if parsed.scheme or parsed.netloc or reference.startswith(("mailto:", "tel:")):
                continue
            if not parsed.path:
                target = page_path
            elif parsed.path.startswith("/"):
                target = output_dir / unquote(parsed.path.lstrip("/"))
            else:
                target = page_path.parent / unquote(parsed.path)
            if str(parsed.path).endswith("/") or target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                errors.append(f"{page_path}: missing local target {reference}")
                continue
            if target.suffix.lower() in CACHEABLE_ASSET_SUFFIXES and not FINGERPRINTED_ASSET_PATTERN.search(target.name):
                errors.append(f"{page_path}: cacheable asset is not fingerprinted: {reference}")
            if parsed.fragment and target.suffix == ".html":
                target_inspector = pages.get(target)
                if target_inspector and parsed.fragment not in target_inspector.ids:
                    errors.append(f"{page_path}: missing fragment target {reference}")
    if errors:
        raise ValueError("Dashboard validation failed:\n" + "\n".join(errors))


def load_resources() -> list[dict[str, object]]:
    payload = json.loads(read_text(SITE_DIR / "resources.json"))
    resources = payload.get("resources", [])
    if not resources:
        raise ValueError("site/resources.json must contain at least one resource")
    seen: set[str] = set()
    required = {
        "slug", "title", "shortTitle", "description", "category", "status",
        "owner", "effectiveDate", "lastReviewed", "version", "audience", "contentFile",
    }
    for resource in resources:
        missing = required - resource.keys()
        if missing:
            raise ValueError(f"Resource is missing fields: {', '.join(sorted(missing))}")
        slug = str(resource["slug"])
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"Invalid resource slug: {slug}")
        if slug in seen:
            raise ValueError(f"Duplicate resource slug: {slug}")
        seen.add(slug)
        content_path = SITE_DIR / "content" / str(resource["contentFile"])
        if not content_path.is_file():
            raise FileNotFoundError(f"Missing resource content: {content_path}")
    return resources


def minify_css(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r"\s+", " ", content)
    content = re.sub(r"\s*([{}:;,>])\s*", r"\1", content)
    return content.replace(";}", "}").strip() + "\n"


def fingerprinted_asset(source: Path, output_dir: Path, output_stem: str, content: bytes | None = None) -> Path:
    payload = source.read_bytes() if content is None else content
    digest = hashlib.sha256(payload).hexdigest()[:FINGERPRINT_LENGTH]
    target = output_dir / f"{output_stem}.{digest}{source.suffix}"
    target.write_bytes(payload)
    return target


def load_contribution_payload(data_source: Path = DEFAULT_CONTRIBUTION_DATA_SOURCE) -> dict[str, object]:
    raw = read_text(data_source).strip()
    prefix = "window.CONTRIBUTION_DATA = "
    if not raw.startswith(prefix) or not raw.endswith(";"):
        raise ValueError(f"{data_source} is not a CONTRIBUTION_DATA payload")
    return json.loads(raw[len(prefix):-1])


def contribution_groups(records: list[list[object]], label_index: int, *, absolute: bool = False) -> list[list[object]]:
    groups: dict[str, int] = {}
    for record in records:
        amount = abs(int(record[5])) if absolute else int(record[5])
        label = str(record[label_index])
        groups[label] = groups.get(label, 0) + amount
    return [
        [label, amount]
        for label, amount in sorted(groups.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]


def contribution_era_leaders(
    records: list[list[object]],
    eras: list[list[object]],
) -> dict[str, list[dict[str, object]]]:
    totals: dict[str, dict[str, int]] = {}
    player_names: dict[str, str] = {}
    for record in records:
        player_id = str(record[1])
        era = str(record[3])
        player_names.setdefault(player_id, str(record[2]))
        era_totals = totals.setdefault(era, {})
        era_totals[player_id] = era_totals.get(player_id, 0) + int(record[5])

    leaders: dict[str, list[dict[str, object]]] = {}
    for era, _amount in eras:
        era_name = str(era)
        ranked = sorted(
            totals.get(era_name, {}).items(),
            key=lambda item: (
                -item[1],
                player_names[item[0]].casefold(),
                item[0],
            ),
        )[:CONTRIBUTION_ERA_LEADER_LIMIT]
        leaders[era_name] = [
            {
                "id": player_id,
                "name": player_names[player_id],
                "total": amount,
            }
            for player_id, amount in ranked
        ]
    return leaders


def build_contribution_summary_payload(payload: dict[str, object]) -> dict[str, object]:
    records = list(payload["records"])
    latest = dt.datetime.fromisoformat(str(payload["meta"]["latestTimestamp"]))
    latest_date = latest.date()
    positive_records = [record for record in records if int(record[5]) > 0]
    first_positive_date = min(
        (dt.date.fromisoformat(str(record[0])[:10]) for record in positive_records),
        default=latest_date,
    )
    periods: dict[str, object] = {}
    for key, days in CONTRIBUTION_PERIODS:
        cutoff_date = latest_date - dt.timedelta(days=days - 1)
        start_date = max(cutoff_date, first_positive_date)
        cutoff = start_date.isoformat()
        current = [record for record in positive_records if str(record[0])[:10] >= cutoff]
        contribution_days = max(1, (latest_date - start_date).days + 1)

        by_player: dict[str, list[list[object]]] = {}
        for record in current:
            by_player.setdefault(str(record[1]), []).append(record)
        producers = []
        for player_id, member_records in by_player.items():
            total = sum(int(record[5]) for record in member_records)
            eras = contribution_groups(member_records, 3)
            producers.append(
                {
                    "id": player_id,
                    "name": str(member_records[0][2]),
                    "total": total,
                    "count": len(member_records),
                    "topEra": eras[0][0] if eras else "",
                    "goods": contribution_groups(member_records, 4)[:8],
                    "eras": eras[:8],
                    "sources": contribution_groups(member_records, 6)[:8],
                }
            )
        producers.sort(key=lambda producer: (-int(producer["total"]), str(producer["name"]).casefold()))
        total = sum(int(record[5]) for record in current)
        eras = contribution_groups(current, 3)[:8]
        periods[key] = {
            "startDate": start_date.isoformat(),
            "endDate": latest_date.isoformat(),
            "recordCount": len(current),
            "total": total,
            "dailyAverage": int(total / contribution_days + 0.5),
            "producers": producers,
            "eras": eras,
            "eraContributors": contribution_era_leaders(current, eras),
        }
    return {"meta": payload["meta"], "periods": periods}


def build_admin_usage_periods(
    records: list[list[object]],
    latest_date: dt.date,
) -> dict[str, object]:
    usage_records = [record for record in records if int(record[5]) < 0]
    periods: dict[str, object] = {}
    for key, days in CONTRIBUTION_PERIODS:
        cutoff = (latest_date - dt.timedelta(days=days - 1)).isoformat()
        current = [record for record in usage_records if str(record[0])[:10] >= cutoff]
        grouped: dict[tuple[str, str], list[list[object]]] = {}
        for record in current:
            group_key = (str(record[1]), str(record[6]))
            grouped.setdefault(group_key, []).append(record)

        rows = []
        for (player_id, purpose), group_records in grouped.items():
            rows.append(
                {
                    "playerId": player_id,
                    "playerName": str(group_records[0][2]),
                    "purpose": purpose,
                    "total": sum(abs(int(record[5])) for record in group_records),
                    "recordCount": len(group_records),
                    "goods": contribution_groups(group_records, 4, absolute=True),
                }
            )
        rows.sort(
            key=lambda row: (
                -int(row["total"]),
                str(row["playerName"]).casefold(),
                str(row["purpose"]).casefold(),
            )
        )
        periods[key] = {
            "recordCount": len(current),
            "total": sum(abs(int(record[5])) for record in current),
            "playerCount": len({str(record[1]) for record in current}),
            "purposeCount": len({str(record[6]) for record in current}),
            "rows": rows,
        }
    return periods


def publish_contribution_assets(
    data_source: Path,
    output_dir: Path,
) -> tuple[Path, list[Path]]:
    payload = load_contribution_payload(data_source)
    latest_date = dt.datetime.fromisoformat(str(payload["meta"]["latestTimestamp"])).date()
    records_by_player: dict[str, list[list[object]]] = {}
    for record in payload["records"]:
        records_by_player.setdefault(str(record[1]), []).append(record)
    admin_usage_periods = build_admin_usage_periods(list(payload["records"]), latest_date)

    detail_assets: list[Path] = []
    detail_urls: dict[str, str] = {}
    detail_source = Path("contribution-detail.json")
    for player_id in sorted(records_by_player):
        records = sorted(records_by_player[player_id], key=lambda record: str(record[0]), reverse=True)
        contribution_records = [record for record in records if int(record[5]) > 0]
        usage_records = [record for record in records if int(record[5]) < 0]
        contribution_record_counts: dict[str, int] = {}
        usage_periods: dict[str, object] = {}
        for key, days in CONTRIBUTION_PERIODS:
            cutoff = (latest_date - dt.timedelta(days=days - 1)).isoformat()
            contribution_record_counts[key] = sum(
                1 for record in contribution_records if str(record[0])[:10] >= cutoff
            )
            current_usage = [record for record in usage_records if str(record[0])[:10] >= cutoff]
            usage_periods[key] = {
                "recordCount": len(current_usage),
                "total": sum(abs(int(record[5])) for record in current_usage),
                "purposes": contribution_groups(current_usage, 6, absolute=True)[:8],
                "goods": contribution_groups(current_usage, 4, absolute=True)[:8],
                "eras": contribution_groups(current_usage, 3, absolute=True)[:8],
            }
        detail_payload = {
            "playerId": player_id,
            "playerName": str(records[0][2]),
            "recordLimit": CONTRIBUTION_DETAIL_RECORD_LIMIT,
            "availableRecordCount": len(contribution_records),
            "contributionRecordCounts": contribution_record_counts,
            "records": contribution_records[:CONTRIBUTION_DETAIL_RECORD_LIMIT],
            "usagePeriods": usage_periods,
        }
        if player_id == ADMIN_CONTRIBUTION_PLAYER_ID:
            detail_payload["adminUsagePeriods"] = admin_usage_periods
        content = json.dumps(detail_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        target = fingerprinted_asset(detail_source, output_dir, "contribution-detail", content)
        detail_assets.append(target)
        detail_urls[player_id] = f"/{target.name}"

    summary_payload = build_contribution_summary_payload(payload)
    summary_payload["details"] = detail_urls
    summary_content = (
        "window.CONTRIBUTION_SUMMARY = "
        + json.dumps(summary_payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    ).encode("utf-8")
    summary_target = fingerprinted_asset(
        Path("contribution-summary.js"),
        output_dir,
        "contribution-summary",
        summary_content,
    )
    return summary_target, detail_assets


def remove_stale_published_assets(output_dir: Path, current: set[Path]) -> None:
    legacy_names = {"GOE.png", "app.js", "data.js", "portal-banner.jpg", "styles.css"}
    for candidate in output_dir.iterdir():
        if not candidate.is_file() or candidate in current:
            continue
        if candidate.name in legacy_names or FINGERPRINTED_ASSET_PATTERN.search(candidate.name):
            candidate.unlink()


def publish_assets(
    output_dir: Path,
    data_source: Path = DEFAULT_DATA_SOURCE,
    contribution_data_source: Path = DEFAULT_CONTRIBUTION_DATA_SOURCE,
) -> dict[str, Path]:
    sources: dict[str, tuple[Path, str]] = {
        "styles": (ASSET_SOURCE_DIR / "styles.css", "styles"),
        "data": (data_source, "data"),
        "app": (ASSET_SOURCE_DIR / "app.js", "app"),
        "contributions_app": (ASSET_SOURCE_DIR / "contributions.js", "contributions"),
        "icon": (ASSET_SOURCE_DIR / "GOE.png", "GOE"),
    }
    for image_format in BANNER_FORMATS:
        for width in BANNER_WIDTHS:
            sources[f"banner_{image_format}_{width}"] = (
                ASSET_SOURCE_DIR / f"portal-banner-{width}.{image_format}",
                f"portal-banner-{width}",
            )
    missing = [path.name for path, _ in sources.values() if not path.is_file()]
    if not contribution_data_source.is_file():
        missing.append(contribution_data_source.name)
    if missing:
        raise FileNotFoundError(f"Missing dashboard asset files: {', '.join(missing)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    targets: dict[str, Path] = {}
    for name, (source, output_stem) in sources.items():
        content = minify_css(read_text(source)).encode() if name == "styles" else None
        targets[name] = fingerprinted_asset(source, output_dir, output_stem, content)
    contribution_summary, contribution_details = publish_contribution_assets(
        contribution_data_source,
        output_dir,
    )
    targets["contribution_summary"] = contribution_summary
    remove_stale_published_assets(output_dir, set(targets.values()) | set(contribution_details))
    return targets


def load_treasury_summary(data_source: Path = DEFAULT_DATA_SOURCE) -> dict[str, str]:
    raw = read_text(data_source).strip()
    prefix = "window.TREASURY_DATA = "
    if not raw.startswith(prefix) or not raw.endswith(";"):
        raise ValueError(f"{data_source} is not a TREASURY_DATA payload")
    payload = json.loads(raw[len(prefix):-1])
    goods = payload["goods"]
    current_values = [good["values"][-1] for good in goods]
    threshold = payload["meta"]["lowStockThreshold"]
    critical_count = sum(value < threshold for value in current_values)
    latest = dt.date.fromisoformat(payload["meta"]["latestDate"])
    return {
        "treasury_total": f"{sum(current_values):,}",
        "treasury_as_of": latest.strftime("%B %-d, %Y"),
        "treasury_status": (
            "All tracked goods are above the critical threshold."
            if critical_count == 0
            else f"{critical_count} tracked {'good needs' if critical_count == 1 else 'goods need'} attention."
        ),
    }


def load_contribution_summary(data_source: Path = DEFAULT_CONTRIBUTION_DATA_SOURCE) -> dict[str, str]:
    payload = load_contribution_payload(data_source)
    public_summary = build_contribution_summary_payload(payload)
    default_period = public_summary["periods"][DEFAULT_CONTRIBUTION_PERIOD]
    positive_records = [
        record
        for record in payload["records"]
        if record[5] > 0
        and default_period["startDate"] <= str(record[0])[:10] <= default_period["endDate"]
    ]
    total = sum(record[5] for record in positive_records)
    direct = sum(record[5] for record in positive_records if record[6] == "Guild treasury donation")
    first = dt.datetime.combine(dt.date.fromisoformat(default_period["startDate"]), dt.time())
    latest = dt.datetime.combine(dt.date.fromisoformat(default_period["endDate"]), dt.time())
    if first.date() == latest.date():
        date_range = f"{first:%B} {first.day}, {first.year}"
    elif first.year == latest.year and first.month == latest.month:
        date_range = f"{first:%B} {first.day}–{latest.day}, {latest.year}"
    elif first.year == latest.year:
        date_range = f"{first:%B} {first.day}–{latest:%B} {latest.day}, {latest.year}"
    else:
        date_range = f"{first:%B} {first.day}, {first.year}–{latest:%B} {latest.day}, {latest.year}"
    leader = default_period["producers"][0] if default_period["producers"] else None
    period_label = (
        f"{dt.date.fromisoformat(default_period['startDate']):%b} "
        f"{dt.date.fromisoformat(default_period['startDate']).day}, "
        f"{dt.date.fromisoformat(default_period['startDate']).year} to "
        f"{dt.date.fromisoformat(default_period['endDate']):%b} "
        f"{dt.date.fromisoformat(default_period['endDate']).day}, "
        f"{dt.date.fromisoformat(default_period['endDate']).year}"
    )
    producer_rows = []
    for rank, producer in enumerate(default_period["producers"][:10], start=1):
        share = int(producer["total"]) / max(int(default_period["total"]), 1) * 100
        top_era = re.sub(r"^\d+\s*-\s*", "", str(producer["topEra"])) or "—"
        name = html.escape(str(producer["name"]))
        producer_rows.append(
            f'<tr data-producer-id="{html.escape(str(producer["id"]), quote=True)}" tabindex="0" '
            f'aria-label="Open contribution details for {name}">'
            f'<td><span class="producer-rank">{rank}</span></td><td><strong>{name}</strong></td>'
            f'<td class="production-value">{int(producer["total"]):,}</td><td>{share:.1f}%</td>'
            f'<td>{int(producer["count"]):,}</td><td>{html.escape(top_era)}</td></tr>'
        )
    era_rows = []
    eras = default_period["eras"]
    era_contributors = default_period["eraContributors"]
    maximum = int(eras[0][1]) if eras else 1
    for rank, (era, amount) in enumerate(eras, start=1):
        era_key = str(era)
        label = html.escape(re.sub(r"^\d+\s*-\s*", "", era_key))
        share = int(amount) / max(int(default_period["total"]), 1) * 100
        width = max(3, int(amount) / maximum * 100)
        contributor_rows = []
        for contributor_rank, contributor in enumerate(era_contributors[era_key], start=1):
            contributor_rows.append(
                f'<li><span><span class="era-contributor-rank">{contributor_rank}</span>'
                f'<strong>{html.escape(str(contributor["name"]))}</strong></span>'
                f'<strong>{int(contributor["total"]):,}</strong></li>'
            )
        era_rows.append(
            '<li class="era-production-item"><details class="era-production-detail"><summary>'
            f'<span class="era-production-rank">{rank}</span>'
            f'<span class="era-production-summary"><strong>{label}</strong>'
            f'<small>{share:.1f}% of contributions</small>'
            f'<span class="era-production-bar" style="--era-width:{width:.2f}%"></span></span>'
            f'<strong class="era-production-total">{int(amount):,}</strong>'
            '<span class="era-production-expander" aria-hidden="true"></span></summary>'
            '<div class="era-contributors"><span>Top contributors in this period</span>'
            f'<ol>{"".join(contributor_rows)}</ol></div></details></li>'
        )
    return {
        "contribution_total": f"{total:,}",
        "contribution_members": f"{len({record[1] for record in positive_records}):,}",
        "contribution_building": f"{total - direct:,}",
        "contribution_direct": f"{direct:,}",
        "contribution_date_range": date_range,
        "contribution_coverage": (
            f"{period_label} · {int(default_period['recordCount']):,} contribution "
            f"{'record' if int(default_period['recordCount']) == 1 else 'records'} available"
        ),
        "contribution_daily": f"{int(default_period['dailyAverage']):,}",
        "contribution_leader": html.escape(str(leader["name"])) if leader else "—",
        "contribution_leader_total": (
            f"{int(leader['total']):,} goods contributed" if leader else "No contributions in this period"
        ),
        "contribution_top_rows": "".join(producer_rows),
        "contribution_era_rows": "".join(era_rows),
    }


def navigation(active: str) -> str:
    items = [
        ("home", "/", "Home"),
        ("treasury", "/treasury/", "Treasury"),
        ("resources", "/resources/", "Resources"),
    ]
    links = []
    for key, href, label in items:
        current = ' aria-current="page"' if key == active else ""
        links.append(f'<a href="{href}"{current}>{label}</a>')
    return "".join(links)


def resource_cards(resources: list[dict[str, object]], compact: bool = False) -> str:
    cards = []
    for resource in resources:
        slug = html.escape(str(resource["slug"]), quote=True)
        title = html.escape(str(resource["title"]))
        description = html.escape(str(resource["description"]))
        category = html.escape(str(resource["category"]))
        status = html.escape(str(resource["status"]))
        status_class = " status-chip--official" if str(resource["status"]).strip().lower() == "official" else ""
        card_class = "resource-card resource-card--compact" if compact else "resource-card"
        cards.append(
            f'<a class="{card_class}" href="/resources/{slug}/">'
            f'<span class="resource-card__meta"><span>{category}</span><span class="status-chip{status_class}">{status}</span></span>'
            f'<strong>{title}</strong><span class="resource-card__description">{description}</span>'
            '<span class="text-link">Read the resource <span aria-hidden="true">&rarr;</span></span></a>'
        )
    return "".join(cards)


def table_of_contents(content: str) -> str:
    links = []
    for match in HEADING_PATTERN.finditer(content):
        anchor = match.group("anchor")
        label = html.unescape(TAG_PATTERN.sub("", match.group("label"))).strip()
        subsection_class = ' class="toc-link--subsection"' if match.group("level") == "3" else ""
        links.append(
            f'<a{subsection_class} href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a>'
        )
    if not links:
        raise ValueError("Resource content must include h2 headings with ids")
    return "".join(links)


def review_notice(resource: dict[str, object]) -> str:
    if str(resource["status"]).strip().lower() == "official":
        return ""
    note = resource.get("reviewNote", "This resource requires leadership review before publication.")
    return (
        '<aside class="review-banner" aria-labelledby="review-title">'
        '<span class="review-banner__mark" aria-hidden="true">!</span>'
        '<div><strong id="review-title">Leadership review required</strong>'
        f'<p>{html.escape(str(note))}</p></div></aside>'
    )


def page(
    base_template: str,
    *,
    title: str,
    description: str,
    active_nav: str,
    main_class: str,
    content: str,
    styles_asset: str,
    icon_asset: str,
    scripts: str = "",
) -> str:
    return render(
        base_template,
        {
            "title": html.escape(title),
            "description": html.escape(description, quote=True),
            "navigation": navigation(active_nav),
            "main_class": html.escape(main_class, quote=True),
            "content": content,
            "styles_asset": html.escape(styles_asset, quote=True),
            "icon_asset": html.escape(icon_asset, quote=True),
            "scripts": scripts,
            "year": dt.date.today().year,
        },
    )


def redirect_page(*, target: str, styles_asset: str, icon_asset: str) -> str:
    safe_target = html.escape(target, quote=True)
    return (
        "<!doctype html>\n<html lang=\"en\">\n  <head>\n"
        "    <meta charset=\"utf-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"    <meta http-equiv=\"refresh\" content=\"0; url={safe_target}\">\n"
        f"    <link rel=\"canonical\" href=\"{safe_target}\">\n"
        f"    <link rel=\"icon\" href=\"{html.escape(icon_asset, quote=True)}\">\n"
        f"    <link rel=\"stylesheet\" href=\"{html.escape(styles_asset, quote=True)}\">\n"
        "    <title>Member Contributions | GoE Guild Portal</title>\n"
        "  </head>\n  <body>\n"
        "    <main class=\"shell\"><h1>Member Contributions moved</h1>"
        f"<p><a href=\"{safe_target}\">Continue to Member Contributions</a>.</p></main>\n"
        f"    <script>window.location.replace(\"{safe_target}\" + window.location.search + window.location.hash);</script>\n"
        "  </body>\n</html>\n"
    )


def publish_dashboard(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    data_source: Path = DEFAULT_DATA_SOURCE,
    contribution_data_source: Path = DEFAULT_CONTRIBUTION_DATA_SOURCE,
) -> dict[str, Path]:
    output_dir = output_dir.resolve()
    data_source = data_source.resolve()
    contribution_data_source = contribution_data_source.resolve()
    resources = load_resources()
    validate_minimum_font_size()
    assets = publish_assets(output_dir, data_source, contribution_data_source)
    summary = load_treasury_summary(data_source)
    contribution_summary = load_contribution_summary(contribution_data_source)
    base_template = read_text(SITE_DIR / "templates" / "base.html")
    styles_asset = f"/{assets['styles'].name}"
    icon_asset = f"/{assets['icon'].name}"

    home_content = render(
        read_text(SITE_DIR / "pages" / "home.html"),
        {
            **summary,
            **contribution_summary,
            "resource_cards": resource_cards(resources, compact=True),
            "banner_jpg_asset": f"/{assets['banner_jpg_1956'].name}",
            "banner_jpg_srcset": ", ".join(
                f"/{assets[f'banner_jpg_{width}'].name} {width}w" for width in BANNER_WIDTHS
            ),
            "banner_webp_srcset": ", ".join(
                f"/{assets[f'banner_webp_{width}'].name} {width}w" for width in BANNER_WIDTHS
            ),
            "banner_avif_srcset": ", ".join(
                f"/{assets[f'banner_avif_{width}'].name} {width}w" for width in BANNER_WIDTHS
            ),
        },
    )
    write_text(
        output_dir / "index.html",
        page(
            base_template,
            title="GoE Guild Portal",
            description="GoE Guild Portal tools, treasury health, and official resources.",
            active_nav="home",
            main_class="shell shell--home",
            content=home_content,
            styles_asset=styles_asset,
            icon_asset=icon_asset,
        ),
    )

    treasury_content = render(
        read_text(SITE_DIR / "pages" / "treasury.html"),
        contribution_summary,
    )
    treasury_scripts = (
        f'    <script src="/{assets["data"].name}"></script>\n'
        f'    <script src="/{assets["app"].name}"></script>'
    )
    write_text(
        output_dir / "treasury" / "index.html",
        page(
            base_template,
            title="Treasury | GoE Guild Portal",
            description="Current GoE guild treasury health, movement, and goods requiring attention.",
            active_nav="treasury",
            main_class="shell shell--treasury",
            content=treasury_content,
            styles_asset=styles_asset,
            icon_asset=icon_asset,
            scripts=treasury_scripts,
        ),
    )

    contribution_content = render(
        read_text(SITE_DIR / "pages" / "contributions.html"),
        contribution_summary,
    )
    contribution_scripts = (
        f'    <script defer src="/{assets["contribution_summary"].name}"></script>\n'
        f'    <script defer src="/{assets["contributions_app"].name}"></script>'
    )
    write_text(
        output_dir / "treasury" / "contributions" / "index.html",
        page(
            base_template,
            title="Member Contributions | GoE Guild Portal",
            description=(
                "Individual GoE guild goods contribution rankings, including "
                "building production and direct treasury contributions."
            ),
            active_nav="treasury",
            main_class="shell shell--treasury shell--contributions",
            content=contribution_content,
            styles_asset=styles_asset,
            icon_asset=icon_asset,
            scripts=contribution_scripts,
        ),
    )
    write_text(
        output_dir / "contributions" / "index.html",
        redirect_page(
            target="/treasury/contributions/",
            styles_asset=styles_asset,
            icon_asset=icon_asset,
        ),
    )

    resources_content = render(
        read_text(SITE_DIR / "pages" / "resources.html"),
        {"resource_cards": resource_cards(resources)},
    )
    write_text(
        output_dir / "resources" / "index.html",
        page(
            base_template,
            title="Resources | GoE Guild Portal",
            description="Official GoE guild policies, guides, and shared references.",
            active_nav="resources",
            main_class="shell shell--resources",
            content=resources_content,
            styles_asset=styles_asset,
            icon_asset=icon_asset,
        ),
    )

    resource_template = read_text(SITE_DIR / "pages" / "resource.html")
    for resource in resources:
        article = read_text(SITE_DIR / "content" / str(resource["contentFile"]))
        resource_content = render(
            resource_template,
            {
                "title": html.escape(str(resource["title"])),
                "description": html.escape(str(resource["description"])),
                "category": html.escape(str(resource["category"])),
                "status": html.escape(str(resource["status"])),
                "status_class": " status-chip--official" if str(resource["status"]).strip().lower() == "official" else "",
                "owner": html.escape(str(resource["owner"])),
                "effective_date": html.escape(str(resource["effectiveDate"])),
                "last_reviewed": html.escape(str(resource["lastReviewed"])),
                "version": html.escape(str(resource["version"])),
                "audience": html.escape(str(resource["audience"])),
                "table_of_contents": table_of_contents(article),
                "review_notice": review_notice(resource),
                "article": article,
            },
        )
        slug = str(resource["slug"])
        write_text(
            output_dir / "resources" / slug / "index.html",
            page(
                base_template,
                title=f'{resource["shortTitle"]} | GoE Guild Portal',
                description=str(resource["description"]),
                active_nav="resources",
                main_class="shell shell--policy",
                content=resource_content,
                styles_asset=styles_asset,
                icon_asset=icon_asset,
            ),
        )

    write_text(
        output_dir / "404.html",
        page(
            base_template,
            title="Page Not Found | GoE Guild Portal",
            description="The requested GoE Guild Portal page could not be found.",
            active_nav="",
            main_class="shell shell--not-found",
            content=read_text(SITE_DIR / "pages" / "not-found.html"),
            styles_asset=styles_asset,
            icon_asset=icon_asset,
        ),
    )

    validate_output(output_dir)
    return assets


def main() -> None:
    args = parse_args()
    assets = publish_dashboard(args.output_dir)
    print("Dashboard pages built: /, /treasury/, /treasury/contributions/, /resources/, /404.html")
    print("Published assets: " + ", ".join(path.name for path in assets.values()))


if __name__ == "__main__":
    main()
