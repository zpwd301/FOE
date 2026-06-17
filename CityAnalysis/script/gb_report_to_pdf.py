#!/usr/bin/env python3
"""Render GB analysis artifacts into a single PDF report, including full dataset."""
from __future__ import annotations

import argparse
import csv
import json
import math
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a PDF report from piecewise-fit JSON + plot + TSV dataset."
    )
    parser.add_argument(
        "--metrics-json",
        required=True,
        help="Path to *_full_report_cut_*.json produced by gb_multiscale_piecewise_report.py",
    )
    parser.add_argument(
        "--dataset-tsv",
        default="",
        help="Optional dataset TSV path. Default: source_file in metrics JSON.",
    )
    parser.add_argument(
        "--plot-image",
        default="",
        help="Optional plot image path. Default: outputs.plot in metrics JSON.",
    )
    parser.add_argument(
        "--output-pdf",
        default="",
        help="Output PDF path. Default: same folder as metrics JSON with .pdf extension.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional report title override.",
    )
    parser.add_argument(
        "--server-label",
        default="beta server",
        help="Server/environment label for summary text (default: beta server).",
    )
    parser.add_argument(
        "--as-of-date",
        default="03/09/2026",
        help="As-of date shown in summary (default: 03/09/2026).",
    )
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return payload


def load_dataset_rows(path: Path) -> Tuple[str, List[Tuple[int, int]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        row1 = next(reader, None)
        row2 = next(reader, None)
        if row1 is None or row2 is None:
            raise SystemExit(f"Invalid TSV format: {path}")
        gb_name = row1[1].strip() if len(row1) >= 2 else path.stem
        if len(row2) < 2 or row2[0] != "level":
            raise SystemExit(f"Expected header row level/required_points in: {path}")

        rows: List[Tuple[int, int]] = []
        for row in reader:
            if len(row) < 2:
                continue
            try:
                rows.append((int(row[0]), int(row[1])))
            except ValueError:
                continue
    return gb_name, rows


def wrap_lines(lines: List[str], width: int = 90) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        if line.startswith("- "):
            chunks = textwrap.wrap(line, width=width, break_long_words=True, subsequent_indent="  ")
        elif line.startswith("  "):
            chunks = textwrap.wrap(line, width=width, break_long_words=True, subsequent_indent="  ")
        else:
            chunks = textwrap.wrap(line, width=width, break_long_words=True)
        wrapped.extend(chunks if chunks else [""])
    return wrapped


def add_text_pages(pdf: PdfPages, title: str, lines: List[str]) -> None:
    wrapped = wrap_lines(lines)
    line_height = 0.022
    y_start = 0.93
    y_end = 0.05
    lines_per_page = max(1, int((y_start - y_end) / line_height))

    for page_idx in range(0, len(wrapped), lines_per_page):
        page_no = page_idx // lines_per_page + 1
        page_lines = wrapped[page_idx : page_idx + lines_per_page]

        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        heading = title if page_no == 1 else f"{title} (cont. {page_no})"
        ax.text(0.05, 0.97, heading, va="top", ha="left", fontsize=16, fontweight="bold")

        y = y_start
        for line in page_lines:
            ax.text(0.05, y, line, va="top", ha="left", fontsize=10, family="monospace")
            y -= line_height

        pdf.savefig(fig)
        plt.close(fig)


def add_plot_page(pdf: PdfPages, title: str, image_path: Path) -> None:
    image = plt.imread(image_path)
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0.05, 0.06, 0.90, 0.90])
    ax.axis("off")
    ax.set_title(title, fontsize=13, pad=8)
    ax.imshow(image, interpolation="none")
    pdf.savefig(fig)
    plt.close(fig)


def add_dataset_pages(pdf: PdfPages, gb_name: str, rows: List[Tuple[int, int]], dataset_name: str) -> None:
    rows_per_page = 70
    total_pages = max(1, math.ceil(len(rows) / rows_per_page))

    for page_idx in range(total_pages):
        start = page_idx * rows_per_page
        end = min(start + rows_per_page, len(rows))
        chunk = rows[start:end]

        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        ax.text(
            0.05,
            0.97,
            f"{gb_name} Dataset (page {page_idx + 1}/{total_pages})",
            va="top",
            ha="left",
            fontsize=14,
            fontweight="bold",
        )
        ax.text(0.05, 0.945, f"Dataset file: {dataset_name}", va="top", ha="left", fontsize=9, family="monospace")
        ax.text(0.05, 0.92, "level    required_points", va="top", ha="left", fontsize=10, family="monospace")

        y = 0.90
        for level, points in chunk:
            ax.text(0.05, y, f"{level:<8} {points:,}", va="top", ha="left", fontsize=10, family="monospace")
            y -= 0.012

        pdf.savefig(fig)
        plt.close(fig)


def level_map(rows: List[Tuple[int, int]]) -> Dict[int, int]:
    return {level: points for level, points in rows}


def nearest_lower(existing_levels: List[int], target: int) -> int | None:
    candidates = [v for v in existing_levels if v < target]
    return max(candidates) if candidates else None


def nearest_upper(existing_levels: List[int], target: int) -> int | None:
    candidates = [v for v in existing_levels if v > target]
    return min(candidates) if candidates else None


def boundary_summary(rows_map: Dict[int, int], boundary: int) -> List[str]:
    levels = sorted(rows_map.keys())
    lines: List[str] = [f"- Around level {boundary} tier upgrade:"]

    before = boundary - 1
    center = boundary
    after = boundary + 1

    if center not in rows_map:
        lines.append("  center level is missing in the observed dataset.")
        return lines

    if before in rows_map:
        lines.append(f"  {before}->{center}: {rows_map[center] - rows_map[before]:+,}")
    else:
        nlow = nearest_lower(levels, center)
        if nlow is not None:
            lines.append(f"  nearest lower observed {nlow}->{center}: {rows_map[center] - rows_map[nlow]:+,}")

    if after in rows_map:
        lines.append(f"  {center}->{after}: {rows_map[after] - rows_map[center]:+,}")
    else:
        nup = nearest_upper(levels, center)
        if nup is not None:
            lines.append(f"  nearest upper observed {center}->{nup}: {rows_map[nup] - rows_map[center]:+,}")

    lines.append("  pattern: a sharp increase into the boundary, followed by a drop right after it.")
    return lines


def main() -> None:
    args = parse_args()
    metrics_path = Path(args.metrics_json).expanduser().resolve()
    if not metrics_path.exists():
        raise SystemExit(f"Metrics JSON not found: {metrics_path}")
    payload = load_json(metrics_path)

    source_file = payload.get("source_file")
    output_paths = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    plot_from_json = output_paths.get("plot") if isinstance(output_paths, dict) else ""

    dataset_path = Path(args.dataset_tsv).expanduser().resolve() if args.dataset_tsv else None
    if dataset_path is None:
        if not isinstance(source_file, str) or not source_file:
            raise SystemExit("No dataset path provided and source_file missing in metrics JSON.")
        dataset_path = Path(source_file).expanduser().resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset TSV not found: {dataset_path}")

    plot_path = Path(args.plot_image).expanduser().resolve() if args.plot_image else None
    if plot_path is None:
        if not isinstance(plot_from_json, str) or not plot_from_json:
            raise SystemExit("No plot path provided and outputs.plot missing in metrics JSON.")
        plot_path = Path(plot_from_json).expanduser().resolve()
    if not plot_path.exists():
        raise SystemExit(f"Plot image not found: {plot_path}")

    if args.output_pdf:
        output_pdf = Path(args.output_pdf).expanduser().resolve()
    else:
        output_pdf = metrics_path.with_suffix(".pdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    gb_name, rows = load_dataset_rows(dataset_path)
    dataset_name = dataset_path.name
    plot_name = plot_path.name
    metrics_name = metrics_path.name
    report_title = args.title.strip() or f"{gb_name} Full Analysis Report"

    overall = payload.get("overall_metrics") if isinstance(payload.get("overall_metrics"), dict) else {}
    segment_fits = payload.get("segment_fits") if isinstance(payload.get("segment_fits"), list) else []
    missing_levels = payload.get("missing_levels") if isinstance(payload.get("missing_levels"), list) else []
    cuts = payload.get("cuts") if isinstance(payload.get("cuts"), list) else []

    rows_map = level_map(rows)
    level_min = rows[0][0]
    level_max = rows[-1][0]

    consecutive_deltas: List[int] = []
    for idx in range(1, len(rows)):
        if rows[idx][0] - rows[idx - 1][0] == 1:
            consecutive_deltas.append(rows[idx][1] - rows[idx - 1][1])
    unique_delta_count = len(set(consecutive_deltas))

    summary_lines: List[str] = [
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Summary",
        f"- Scope: FP cost required to level up {gb_name} on the {args.server_label}, as of {args.as_of_date}.",
        "- This report combines three views of the same dataset:",
        "  (1) full progression with 3-piece fit, (2) level 1-100 zoom, (3) level-to-level delta behavior.",
        "- It is written to keep both high-level trends and low-level changes easy to read.",
        "- Special focus: the tier-transition behavior around levels 100 and 200.",
        "",
        "Report Contents",
        f"- GB: {gb_name}",
        f"- Data files used: {dataset_name}, {plot_name}, {metrics_name}",
        f"- Data points: {len(rows)}",
        f"- Level range: {level_min}..{level_max}",
        f"- Cut points for regression: {cuts}",
        f"- Missing levels in range: {len(missing_levels)}",
        f"- Unique consecutive delta values: {unique_delta_count}",
        "",
        "Data Features",
        "- Growth is piecewise and non-uniform across tiers.",
        "- Lower levels grow with smaller increments than mid/high levels.",
        "- The dataset is sparse at high levels (not every level appears in ranking observations).",
        "",
        "Tier-Boundary Jump/Drop Behavior (from delta panel)",
    ]
    summary_lines.extend(boundary_summary(rows_map, 100))
    summary_lines.extend(boundary_summary(rows_map, 200))

    fit_lines: List[str] = [
        "",
        "Piecewise Fit Metrics",
        f"- Overall R^2 : {overall.get('r2')}",
        f"- Overall RMSE: {overall.get('rmse')}",
        f"- Overall MAE : {overall.get('mae')}",
        "",
        "Segment Equations",
    ]
    for seg in segment_fits:
        if not isinstance(seg, dict):
            continue
        slope = seg.get("slope")
        intercept = seg.get("intercept")
        slope_text = f"{float(slope):.4f}" if isinstance(slope, (int, float)) else str(slope)
        intercept_text = f"{float(intercept):.4f}" if isinstance(intercept, (int, float)) else str(intercept)
        fit_lines.append(f"- {seg.get('label')}")
        fit_lines.append(f"  y = {slope_text} * level + {intercept_text}")
        fit_lines.append(
            f"  n={seg.get('n_points')}, R^2={seg.get('r2')}, RMSE={seg.get('rmse')}, MAE={seg.get('mae')}"
        )

    all_text_lines = summary_lines + fit_lines

    with PdfPages(output_pdf) as pdf:
        add_text_pages(pdf, report_title, all_text_lines)
        add_plot_page(pdf, f"{gb_name}: Combined Multi-Scale + Piecewise Fit", plot_path)
        add_dataset_pages(pdf, gb_name, rows, dataset_name)

    print(f"PDF report: {output_pdf}")
    print(f"Dataset rows included: {len(rows)}")


if __name__ == "__main__":
    main()
