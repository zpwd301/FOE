#!/usr/bin/env python3
"""Generate a guild treasury trend and deficit report from CSV snapshots."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter


AGE_ORDER = [
    "Bronze Age",
    "Iron Age",
    "Early Middle Age",
    "High Middle Age",
    "Late Middle Age",
    "Colonial Age",
    "Industrial Age",
    "Progressive Era",
    "Modern Era",
    "Postmodern Era",
    "Contemporary Era",
    "Tomorrow Era",
    "Future Era",
    "Arctic Future",
    "Oceanic Future",
    "Virtual Future",
    "Space Age Mars",
    "Space Age Asteroid Belt",
    "Space Age Venus",
    "Space Age Jupiter Moon",
    "Space Age Titan",
    "Space Age Space Hub",
]
KNOWN_AGES = set(AGE_ORDER)
BRONZE_GOODS = {"wine", "dye", "marble", "lumber", "stone"}
BRONZE_AGE = "bronze age"


@dataclass(frozen=True)
class DataPoint:
    timestamp: dt.datetime
    values: Dict[str, int]


def normalize_name(name: str) -> str:
    return name.strip().lower()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a guild-member treasury PDF report from the latest CSV."
    )
    parser.add_argument(
        "--guild-name",
        type=str,
        default="GoE",
        help="Guild name to display in reports and output filenames (default: GoE).",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("input"),
        help="Folder containing guild treasury CSV files (default: input).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Specific CSV to use. If omitted, newest CSV in input-dir is used.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Number of trailing days to analyze (default: 60).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output folder for generated report (default: output).",
    )
    parser.add_argument(
        "--good-age-map",
        type=Path,
        default=None,
        help=(
            "Optional CSV map for goods-detail data with columns Good,Age. "
            "Used to aggregate goods deficits to age deficits."
        ),
    )
    parser.add_argument(
        "--dip-threshold",
        type=int,
        default=110000,
        help=(
            "Report goods that dip below this amount at any point in the analysis "
            "window (default: 110000)."
        ),
    )
    return parser.parse_args()


def file_key(path: Path) -> Tuple[dt.datetime, dt.datetime, str]:
    filename_date = dt.datetime.min
    match = re.search(r"(\d{8})", path.stem)
    if match:
        try:
            filename_date = dt.datetime.strptime(match.group(1), "%m%d%Y")
        except ValueError:
            filename_date = dt.datetime.min
    modified = dt.datetime.fromtimestamp(path.stat().st_mtime)
    return (modified, filename_date, path.name)


def slugify_name(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "guild"


def find_latest_csv(input_dir: Path) -> Path:
    csv_files = [p for p in input_dir.glob("*.csv") if p.is_file()]
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {input_dir}")
    return max(csv_files, key=file_key)


def parse_int(value: Optional[str]) -> int:
    if value is None:
        return 0
    text = value.strip()
    if not text:
        return 0
    text = text.replace(",", "")
    try:
        return int(text)
    except ValueError:
        return int(float(text))


def parse_timestamp(raw: str) -> dt.datetime:
    text = raw.strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {raw!r}")


def read_treasury_csv(path: Path) -> Tuple[List[str], List[DataPoint]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {path}")

        datetime_col = None
        for header in reader.fieldnames:
            if header.strip().lower() == "datetime":
                datetime_col = header
                break
        if datetime_col is None:
            datetime_col = reader.fieldnames[0]

        value_columns = [h for h in reader.fieldnames if h != datetime_col]
        if not value_columns:
            raise ValueError(f"CSV contains no value columns: {path}")

        rows: List[DataPoint] = []
        for line_no, row in enumerate(reader, start=2):
            raw_dt = (row.get(datetime_col) or "").strip()
            if not raw_dt:
                continue
            try:
                timestamp = parse_timestamp(raw_dt)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc

            values = {col: parse_int(row.get(col)) for col in value_columns}
            rows.append(DataPoint(timestamp=timestamp, values=values))

    if not rows:
        raise ValueError(f"No data rows found in {path}")

    rows.sort(key=lambda item: item.timestamp)
    return value_columns, rows


def read_good_age_map(path: Optional[Path]) -> Dict[str, str]:
    if path is None or not path.exists():
        return {}

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}

        headers = {h.strip().lower(): h for h in reader.fieldnames}
        good_header = headers.get("good")
        age_header = headers.get("age")
        if not good_header or not age_header:
            raise ValueError(
                f"Invalid mapping CSV {path}. Required headers: Good,Age"
            )

        mapping: Dict[str, str] = {}
        for row in reader:
            good = (row.get(good_header) or "").strip()
            age = (row.get(age_header) or "").strip()
            if good and age:
                mapping[good] = age
        return mapping


def select_window(rows: Sequence[DataPoint], days: int) -> List[DataPoint]:
    end_ts = rows[-1].timestamp
    start_ts = end_ts - dt.timedelta(days=days)
    window = [row for row in rows if row.timestamp >= start_ts]
    if len(window) < 2 and len(rows) >= 2:
        window = list(rows[-2:])
    return window


def compute_totals(rows: Sequence[DataPoint]) -> List[Tuple[dt.datetime, int]]:
    return [(row.timestamp, sum(row.values.values())) for row in rows]


def compute_changes(
    rows: Sequence[DataPoint], columns: Iterable[str]
) -> List[Tuple[str, int, int, int]]:
    first = rows[0].values
    last = rows[-1].values
    changes = []
    for col in columns:
        start = first.get(col, 0)
        end = last.get(col, 0)
        delta = end - start
        changes.append((col, start, end, delta))
    return sorted(changes, key=lambda item: item[3])


def aggregate_age_changes_from_goods(
    good_changes: Sequence[Tuple[str, int, int, int]],
    good_age_map: Dict[str, str],
) -> Tuple[List[Tuple[str, int, int, int]], List[str]]:
    age_rollup: Dict[str, List[int]] = {}
    unmapped: List[str] = []
    for good, start, end, _ in good_changes:
        age = good_age_map.get(good)
        if not age:
            unmapped.append(good)
            continue
        age_rollup.setdefault(age, [0, 0])
        age_rollup[age][0] += start
        age_rollup[age][1] += end

    age_changes = []
    for age, (start, end) in age_rollup.items():
        age_changes.append((age, start, end, end - start))
    age_changes.sort(key=lambda item: item[3])
    return age_changes, sorted(unmapped)


def infer_good_age_map_by_order(columns: Sequence[str]) -> Dict[str, str]:
    # FoE treasury export commonly groups goods by age in blocks of 5 columns.
    if len(columns) % 5 != 0:
        return {}

    group_count = len(columns) // 5
    if group_count == len(AGE_ORDER):
        start_idx = 0
    elif group_count == len(AGE_ORDER) - 1:
        start_idx = 1
    else:
        return {}

    mapping: Dict[str, str] = {}
    for idx, good in enumerate(columns):
        age_idx = start_idx + (idx // 5)
        if age_idx >= len(AGE_ORDER):
            return {}
        mapping[good] = AGE_ORDER[age_idx]
    return mapping


def infer_mode(columns: Sequence[str]) -> str:
    if columns and set(columns).issubset(KNOWN_AGES):
        return "age_aggregated"
    return "goods_detail"


def filter_analysis_columns(
    mode: str, columns: Sequence[str]
) -> Tuple[List[str], List[str]]:
    included: List[str] = []
    excluded: List[str] = []
    for col in columns:
        key = normalize_name(col)
        is_bronze = key == BRONZE_AGE if mode == "age_aggregated" else key in BRONZE_GOODS
        if is_bronze:
            excluded.append(col)
        else:
            included.append(col)
    return included, excluded


def project_rows(rows: Sequence[DataPoint], columns: Sequence[str]) -> List[DataPoint]:
    selected = set(columns)
    projected: List[DataPoint] = []
    for row in rows:
        values = {k: v for k, v in row.values.items() if k in selected}
        projected.append(DataPoint(timestamp=row.timestamp, values=values))
    return projected


def fmt_num(value: int) -> str:
    return f"{value:,}"


def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


@dataclass(frozen=True)
class TrendSummary:
    start_ts: dt.datetime
    end_ts: dt.datetime
    start_total: int
    end_total: int
    net_change: int
    pct_change: Optional[float]
    avg_daily_change: float


def build_trend_summary(rows: Sequence[DataPoint]) -> TrendSummary:
    totals = compute_totals(rows)
    start_ts, start_total = totals[0]
    end_ts, end_total = totals[-1]
    net_change = end_total - start_total
    days_span = (end_ts - start_ts).days
    avg_daily = net_change / days_span if days_span > 0 else float(net_change)
    pct_change = (net_change / start_total * 100.0) if start_total else None
    return TrendSummary(
        start_ts=start_ts,
        end_ts=end_ts,
        start_total=start_total,
        end_total=end_total,
        net_change=net_change,
        pct_change=pct_change,
        avg_daily_change=avg_daily,
    )


def classify_health(summary: TrendSummary) -> str:
    pct = summary.pct_change or 0.0
    if pct >= 1.0:
        return "in strong shape"
    if pct >= 0.0:
        return "stable with healthy growth"
    if pct > -0.5:
        return "mostly stable with a small decline"
    return "under pressure and needs attention"


def signed_num(value: int) -> str:
    return f"{value:+,}"


def list_with_limit(items: Sequence[str], max_items: int) -> str:
    if not items:
        return "None"
    if len(items) <= max_items:
        return ", ".join(items)
    head = ", ".join(items[:max_items])
    return f"{head}, and {len(items) - max_items} more"


def _render_table(
    fig: plt.Figure,
    rect: Sequence[float],
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    font_size: float = 9.0,
    header_color: str = "#ffe9d9",
    edge_color: str = "#d8dde6",
    col_widths: Optional[Sequence[float]] = None,
) -> None:
    def _auto_col_widths(
        hdrs: Sequence[str], body_rows: Sequence[Sequence[str]]
    ) -> List[float]:
        col_sizes: List[int] = []
        for idx, header in enumerate(hdrs):
            longest = len(str(header))
            for row in body_rows:
                if idx < len(row):
                    longest = max(longest, len(str(row[idx])))
            col_sizes.append(longest + 2)
        total = sum(col_sizes) or 1
        return [size / total for size in col_sizes]

    ax = fig.add_axes(rect)
    ax.axis("off")
    ax.text(
        0.0,
        1.06,
        title,
        fontsize=12,
        fontweight="bold",
        ha="left",
        va="bottom",
        transform=ax.transAxes,
    )
    if col_widths is None:
        col_widths = _auto_col_widths(headers, rows)
    table = ax.table(
        cellText=list(rows),
        colLabels=list(headers),
        loc="upper left",
        cellLoc="left",
        colLoc="left",
        bbox=[0.0, 0.0, 1.0, 0.98],
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(1.0, 1.12)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor(edge_color)
        if row_idx == 0:
            cell.set_facecolor(header_color)
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor("white")


def render_member_pdf(
    guild_name: str,
    output_path: Path,
    analysis_days: int,
    totals: Sequence[Tuple[dt.datetime, int]],
    summary: TrendSummary,
    age_changes: Sequence[Tuple[str, int, int, int]],
    goods_below_threshold: Sequence[Tuple[str, str, int, dt.datetime]],
    dip_threshold: int,
) -> None:
    health_text = classify_health(summary)
    deficit_ages = [row for row in age_changes if row[3] < 0]
    age_names = [row[0] for row in deficit_ages]
    dip_goods_names = [row[0] for row in goods_below_threshold]

    colors = {
        "page_bg": "#f7fafc",
        "header_bg": "#0b2c4d",
        "header_text": "#f8fbff",
        "accent": "#ff6b35",
        "accent2": "#00a8a8",
        "title_text": "#0f172a",
        "body_text": "#1f2937",
        "muted": "#475569",
        "panel": "#ffffff",
        "grid": "#d8e2f0",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(output_path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
        fig.patch.set_facecolor(colors["page_bg"])
        fig.add_artist(Rectangle((0.0, 0.90), 1.0, 0.10, transform=fig.transFigure, color=colors["header_bg"]))
        fig.add_artist(Rectangle((0.0, 0.90), 0.33, 0.01, transform=fig.transFigure, color=colors["accent"]))
        fig.add_artist(Rectangle((0.33, 0.90), 0.33, 0.01, transform=fig.transFigure, color=colors["accent2"]))
        fig.add_artist(Rectangle((0.66, 0.90), 0.34, 0.01, transform=fig.transFigure, color="#5e60ce"))

        fig.text(
            0.07,
            0.957,
            f"{guild_name} Guild Treasury Report",
            fontsize=21,
            fontweight="bold",
            color=colors["header_text"],
        )
        fig.text(
            0.07,
            0.924,
            f"Executive Summary | Last {analysis_days} days ({summary.start_ts:%b %d, %Y} - {summary.end_ts:%b %d, %Y})",
            fontsize=11,
            color="#dbeafe",
        )

        if age_names:
            age_summary = (
                f"{len(age_names)} ages in deficit: "
                f"{list_with_limit(age_names, 4)}"
            )
        else:
            age_summary = "No age-level deficits in this period."

        if dip_goods_names:
            dip_summary = (
                f"{len(dip_goods_names)} goods dipped below {fmt_num(dip_threshold)}: "
                f"{list_with_limit(dip_goods_names, 4)}"
            )
        else:
            dip_summary = f"No goods dipped below {fmt_num(dip_threshold)} during this period."

        summary_lines = [
            f"Overall treasury health is {health_text} over the past {analysis_days} days.",
            f"Total goods changed from {fmt_num(summary.start_total)} to {fmt_num(summary.end_total)} ({signed_num(summary.net_change)}, {fmt_pct(summary.pct_change)}).",
            f"Average daily movement: {signed_num(int(round(summary.avg_daily_change)))} goods.",
            age_summary,
            dip_summary,
        ]

        y = 0.875
        for line in summary_lines:
            wrapped = textwrap.wrap(line, width=86)
            for idx, segment in enumerate(wrapped):
                prefix = "- " if idx == 0 else "  "
                fig.text(0.08, y, f"{prefix}{segment}", fontsize=11, color=colors["body_text"], va="top")
                y -= 0.026
            y -= 0.004

        ax = fig.add_axes([0.11, 0.17, 0.80, 0.47])
        ax.set_facecolor(colors["panel"])
        for spine in ax.spines.values():
            spine.set_color("#c7d2e3")
            spine.set_linewidth(1.0)
        dates = [item[0] for item in totals]
        values = [item[1] for item in totals]
        values_m = [v / 1_000_000 for v in values]
        min_m = min(values_m)
        max_m = max(values_m)
        pad_m = max((max_m - min_m) * 0.20, 0.05)
        ax.plot(dates, values_m, color=colors["accent"], linewidth=2.8, marker="o", markersize=2.8, zorder=3)
        ax.fill_between(dates, values_m, min_m - pad_m, color=colors["accent2"], alpha=0.10, zorder=1)
        ax.scatter([dates[0], dates[-1]], [values_m[0], values_m[-1]], color=colors["header_bg"], s=45, zorder=4)
        ax.set_title("Overall Treasury Trend", fontsize=13, fontweight="bold", pad=12, color=colors["title_text"])
        ax.set_ylabel("Total Goods (Millions)", fontsize=10, color=colors["body_text"], labelpad=2)
        ax.grid(True, color=colors["grid"], linewidth=0.8, alpha=0.95)
        ax.tick_params(axis="x", labelrotation=0, labelsize=8.5, colors=colors["muted"], pad=2)
        ax.tick_params(axis="y", labelsize=9, colors=colors["muted"])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.2f}M"))
        ax.set_ylim(min_m - pad_m, max_m + pad_m)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.margins(x=0.03)
        ax.text(dates[0], values_m[0], f"Start {fmt_num(values[0])}", fontsize=8.5, va="bottom", color=colors["body_text"])
        ax.text(dates[-1], values_m[-1], f"End {fmt_num(values[-1])}", fontsize=8.5, va="bottom", ha="right", color=colors["body_text"])
        fig.text(
            0.08,
            0.115,
            "Bronze Age goods are excluded from this report (Wine, Dye, Marble, Lumber, Stone).",
            fontsize=9,
            color=colors["muted"],
        )
        pdf.savefig(fig)
        plt.close(fig)

        fig2 = plt.figure(figsize=(8.27, 11.69))
        fig2.patch.set_facecolor(colors["page_bg"])
        fig2.add_artist(Rectangle((0.0, 0.92), 1.0, 0.08, transform=fig2.transFigure, color=colors["header_bg"]))
        fig2.text(
            0.07,
            0.955,
            f"{guild_name} Deficit Watch List",
            fontsize=19,
            fontweight="bold",
            color=colors["header_text"],
        )
        fig2.text(0.07, 0.925, "Priority areas to monitor and refill.", fontsize=11, color="#dbeafe")

        chart_rows = deficit_ages[:8]
        if chart_rows:
            chart_labels = [item[0] if len(item[0]) <= 20 else item[0][:19] + "…" for item in chart_rows][::-1]
            chart_values = [abs(item[3]) for item in chart_rows][::-1]
            ax_age = fig2.add_axes([0.14, 0.56, 0.44, 0.30])
            ax_age.barh(chart_labels, chart_values, color=colors["accent2"], edgecolor="#0f766e", linewidth=0.8)
            ax_age.set_title("Largest Age Deficits", fontsize=12, fontweight="bold", pad=10, color=colors["title_text"])
            ax_age.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
            ax_age.grid(axis="x", color=colors["grid"], linewidth=0.8, alpha=0.9)
            ax_age.tick_params(axis="x", labelsize=8, colors=colors["muted"])
            ax_age.tick_params(axis="y", labelsize=7.5, colors=colors["body_text"], pad=1)
        else:
            fig2.text(0.08, 0.71, "No age deficits in this period.", fontsize=11, color=colors["body_text"])

        age_rows: List[List[str]] = [[name, signed_num(delta)] for name, _, _, delta in deficit_ages]
        if not age_rows:
            age_rows = [["No age deficits in this period", "0"]]
        age_omitted = max(0, len(age_rows) - 10)
        _render_table(
            fig2,
            rect=[0.62, 0.56, 0.30, 0.30],
            title="Ages in Deficit",
            headers=["Age", "Net Change"],
            rows=age_rows[:10],
            font_size=8.6,
            header_color="#d9ecff",
            edge_color="#c7d6eb",
        )
        if age_omitted:
            fig2.text(0.62, 0.53, f"+ {age_omitted} more ages not shown", fontsize=8.5, color=colors["muted"])

        dip_rows: List[List[str]] = [
            [good, age, fmt_num(min_value), f"{min_ts:%b %d, %Y}"]
            for good, age, min_value, min_ts in goods_below_threshold
        ]
        if not dip_rows:
            dip_rows = [["No goods dipped below threshold", "-", "-", "-"]]
        dip_omitted = max(0, len(dip_rows) - 14)
        _render_table(
            fig2,
            rect=[0.08, 0.09, 0.84, 0.39],
            title=f"Goods that Dipped Below {fmt_num(dip_threshold)}",
            headers=["Good", "Age", "Lowest Amount", "Date"],
            rows=dip_rows[:14],
            font_size=8.7,
            header_color="#ffe9d9",
            edge_color="#d9c5b7",
        )
        if dip_omitted:
            fig2.text(0.08, 0.075, f"+ {dip_omitted} more goods not shown", fontsize=8.5, color=colors["muted"])

        fig2.text(
            0.08,
            0.045,
            f"Thank you for supporting {guild_name} and helping keep our treasury healthy.",
            fontsize=10,
            color=colors["body_text"],
        )
        pdf.savefig(fig2)
        plt.close(fig2)

def render_change_table(
    title: str, rows: Sequence[Tuple[str, int, int, int]], deficit_only: bool = True
) -> List[str]:
    lines = [f"## {title}"]
    selected = [r for r in rows if r[3] < 0] if deficit_only else list(rows)
    if not selected:
        lines.append("")
        lines.append("No deficits detected in the selected window.")
        lines.append("")
        return lines

    lines.append("")
    lines.append("| Name | Start | End | Net Change |")
    lines.append("|---|---:|---:|---:|")
    for name, start, end, delta in selected:
        lines.append(f"| {name} | {fmt_num(start)} | {fmt_num(end)} | {fmt_num(delta)} |")
    lines.append("")
    return lines


def compute_goods_below_threshold(
    rows: Sequence[DataPoint],
    goods: Sequence[str],
    threshold: int,
    good_age_map: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, str, int, dt.datetime]]:
    result: List[Tuple[str, str, int, dt.datetime]] = []
    mapping = good_age_map or {}
    for good in goods:
        min_value = None
        min_ts = None
        for row in rows:
            val = row.values.get(good, 0)
            if min_value is None or val < min_value:
                min_value = val
                min_ts = row.timestamp
        if min_value is not None and min_value < threshold and min_ts is not None:
            age_name = mapping.get(good, "Unknown Age")
            result.append((good, age_name, min_value, min_ts))
    result.sort(key=lambda item: (item[2], item[0]))
    return result


def _append_markdown_table(
    lines: List[str],
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    right_align_cols: Optional[Sequence[int]] = None,
) -> None:
    align_set = set(right_align_cols or [])
    align = ["---:" if idx in align_set else "---" for idx in range(len(headers))]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(align) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    lines.append("")


def render_technical_markdown(
    guild_name: str,
    source_csv: Path,
    all_rows: Sequence[DataPoint],
    window_rows: Sequence[DataPoint],
    analysis_days: int,
    mode: str,
    excluded_columns: Sequence[str],
    summary: TrendSummary,
    totals: Sequence[Tuple[dt.datetime, int]],
    age_changes: Sequence[Tuple[str, int, int, int]],
    good_changes: Sequence[Tuple[str, int, int, int]],
    goods_below_threshold: Sequence[Tuple[str, str, int, dt.datetime]],
    dip_threshold: int,
    good_age_map_used: bool,
) -> str:
    lines: List[str] = []
    lines.append(f"# {guild_name} Guild Treasury Technical Report")
    lines.append("")
    lines.append(f"- Source CSV: `{source_csv}`")
    lines.append(f"- Generated at: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append(f"- Full data range: {all_rows[0].timestamp:%Y-%m-%d} to {all_rows[-1].timestamp:%Y-%m-%d}")
    lines.append(f"- Analysis window: {summary.start_ts:%Y-%m-%d} to {summary.end_ts:%Y-%m-%d} ({len(window_rows)} snapshots)")
    lines.append(f"- Analysis days setting: `{analysis_days}`")
    lines.append(f"- Input mode: `{mode}`")
    lines.append(f"- Bronze Age exclusions: {', '.join(excluded_columns) if excluded_columns else 'None'}")
    lines.append(f"- Goods-to-age mapping available: `{'yes' if good_age_map_used else 'no'}`")
    lines.append("")

    lines.append("## Summary Metrics")
    lines.append("")
    metric_rows = [
        ["Start total goods", fmt_num(summary.start_total)],
        ["End total goods", fmt_num(summary.end_total)],
        ["Net change", signed_num(summary.net_change)],
        ["Percent change", fmt_pct(summary.pct_change)],
        ["Average daily net change", f"{summary.avg_daily_change:,.2f}"],
        ["Treasury health classification", classify_health(summary)],
    ]
    _append_markdown_table(lines, ["Metric", "Value"], metric_rows, right_align_cols=[1])

    lines.append("## Age Net Changes")
    lines.append("")
    if age_changes:
        age_rows = [
            [name, fmt_num(start), fmt_num(end), signed_num(delta)]
            for name, start, end, delta in age_changes
        ]
        _append_markdown_table(
            lines,
            ["Age", "Start", "End", "Net Change"],
            age_rows,
            right_align_cols=[1, 2, 3],
        )
    else:
        lines.append("Age-level changes unavailable (goods-to-age mapping not found).")
        lines.append("")

    lines.append("## Goods Net Changes")
    lines.append("")
    if good_changes:
        deficit_rows = [
            [name, fmt_num(start), fmt_num(end), signed_num(delta)]
            for name, start, end, delta in good_changes
            if delta < 0
        ]
        gain_rows = [
            [name, fmt_num(start), fmt_num(end), signed_num(delta)]
            for name, start, end, delta in reversed(good_changes)
            if delta > 0
        ]
        lines.append(f"- Deficit goods count: `{len(deficit_rows)}`")
        lines.append(f"- Surplus goods count: `{len(gain_rows)}`")
        lines.append("")
        if deficit_rows:
            lines.append("### Deficit Goods")
            lines.append("")
            _append_markdown_table(
                lines,
                ["Good", "Start", "End", "Net Change"],
                deficit_rows,
                right_align_cols=[1, 2, 3],
            )
        if gain_rows:
            lines.append("### Surplus Goods")
            lines.append("")
            _append_markdown_table(
                lines,
                ["Good", "Start", "End", "Net Change"],
                gain_rows[:25],
                right_align_cols=[1, 2, 3],
            )
    else:
        lines.append(
            "Good-level changes unavailable because this input contains age-level totals only."
        )
        lines.append("")

    lines.append(f"## Goods Dipped Below {fmt_num(dip_threshold)}")
    lines.append("")
    if goods_below_threshold:
        dip_rows = [
            [good, age, fmt_num(min_value), f"{min_ts:%Y-%m-%d}"]
            for good, age, min_value, min_ts in goods_below_threshold
        ]
        _append_markdown_table(
            lines,
            ["Good", "Age", "Minimum Amount", "Date of Minimum"],
            dip_rows,
            right_align_cols=[2],
        )
    else:
        lines.append("No goods dipped below the threshold in this window.")
        lines.append("")

    lines.append("## Daily Treasury Totals")
    lines.append("")
    daily_rows: List[List[str]] = []
    prev_total: Optional[int] = None
    for day, total in totals:
        delta = 0 if prev_total is None else total - prev_total
        daily_rows.append([f"{day:%Y-%m-%d}", fmt_num(total), signed_num(delta)])
        prev_total = total
    _append_markdown_table(
        lines,
        ["Date", "Total Goods", "Delta vs Previous"],
        daily_rows,
        right_align_cols=[1, 2],
    )

    lines.append("## Notes")
    lines.append("")
    lines.append("- Bronze Age goods are excluded from all calculations.")
    if good_changes and not good_age_map_used:
        lines.append("- Age-level changes in goods mode may be unavailable without a goods-to-age mapping.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if args.days <= 0:
        raise ValueError("--days must be a positive integer.")
    if args.dip_threshold <= 0:
        raise ValueError("--dip-threshold must be a positive integer.")
    guild_name = args.guild_name.strip()
    if not guild_name:
        raise ValueError("--guild-name must not be empty.")

    input_dir = args.input_dir
    source_csv = args.csv if args.csv else find_latest_csv(input_dir)
    if not source_csv.exists():
        raise FileNotFoundError(f"CSV not found: {source_csv}")

    columns, all_rows = read_treasury_csv(source_csv)
    mode = infer_mode(columns)
    analysis_columns, excluded_columns = filter_analysis_columns(mode, columns)
    if not analysis_columns:
        raise ValueError("No columns available for analysis after exclusions.")

    analysis_rows = project_rows(all_rows, analysis_columns)
    window_rows = select_window(analysis_rows, args.days)

    age_changes: List[Tuple[str, int, int, int]] = []
    good_changes: List[Tuple[str, int, int, int]] = []
    goods_below_threshold: List[Tuple[str, str, int, dt.datetime]] = []
    good_age_map_used = False

    if mode == "age_aggregated":
        age_changes = compute_changes(window_rows, analysis_columns)
    else:
        good_changes = compute_changes(window_rows, analysis_columns)
        default_map = input_dir / "good-age-map.csv"
        map_path = args.good_age_map if args.good_age_map is not None else default_map
        good_age_map = read_good_age_map(map_path)
        if not good_age_map:
            good_age_map = infer_good_age_map_by_order(analysis_columns)
        good_age_map_used = bool(good_age_map)
        goods_below_threshold = compute_goods_below_threshold(
            window_rows, analysis_columns, args.dip_threshold, good_age_map
        )
        if good_age_map:
            age_changes, _ = aggregate_age_changes_from_goods(
                good_changes, good_age_map
            )

    totals = compute_totals(window_rows)
    summary = build_trend_summary(window_rows)
    date_range = f"{summary.start_ts:%Y%m%d}-to-{summary.end_ts:%Y%m%d}"
    guild_slug = slugify_name(guild_name)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{guild_slug}-guild-treasury-report-{date_range}-{args.days}d"
    pdf_report_path = args.output_dir / f"{base_name}.pdf"
    md_report_path = args.output_dir / f"{base_name}-technical.md"

    technical_md = render_technical_markdown(
        guild_name=guild_name,
        source_csv=source_csv,
        all_rows=all_rows,
        window_rows=window_rows,
        analysis_days=args.days,
        mode=mode,
        excluded_columns=excluded_columns,
        summary=summary,
        totals=totals,
        age_changes=age_changes,
        good_changes=good_changes,
        goods_below_threshold=goods_below_threshold,
        dip_threshold=args.dip_threshold,
        good_age_map_used=good_age_map_used,
    )
    md_report_path.write_text(technical_md, encoding="utf-8")

    render_member_pdf(
        guild_name=guild_name,
        output_path=pdf_report_path,
        analysis_days=args.days,
        totals=totals,
        summary=summary,
        age_changes=age_changes,
        goods_below_threshold=goods_below_threshold,
        dip_threshold=args.dip_threshold,
    )

    print(f"PDF report generated: {pdf_report_path}")
    print(f"Technical report generated: {md_report_path}")
    print(f"Guild: {guild_name}")
    print(f"Analysis date range: {summary.start_ts:%Y-%m-%d} to {summary.end_ts:%Y-%m-%d}")
    print(f"Snapshots in analysis window: {len(window_rows)}")
    if excluded_columns:
        print("Excluded Bronze Age columns from all calculations.")


if __name__ == "__main__":
    main()
