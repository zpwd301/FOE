#!/usr/bin/env python3
"""Generate a combined multi-scale + piecewise-linear regression report for GB level data."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FuncFormatter, MaxNLocator

from gb_search_query import OUTPUT_DIR, sanitize_filename


@dataclass
class SegmentFit:
    label: str
    min_level: int
    max_level: int
    n_points: int
    slope: float
    intercept: float
    r2: float
    rmse: float
    mae: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create combined multi-scale plot and piecewise regression report for GB required points."
    )
    parser.add_argument(
        "--input-tsv",
        required=True,
        help="Input GB TSV path (format: gb_name row + level/required_points table).",
    )
    parser.add_argument(
        "--cut1",
        type=int,
        default=100,
        help="First cut point (default: 100).",
    )
    parser.add_argument(
        "--cut2",
        type=int,
        default=200,
        help="Second cut point (default: 200).",
    )
    parser.add_argument(
        "--zoom-max",
        type=int,
        default=100,
        help="Max level for lower-level zoom chart (default: 100).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Default: sibling 'graphs' folder of input TSV.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=360,
        help="PNG output DPI for combined plot (default: 360).",
    )
    return parser.parse_args()


def parse_int(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def load_gb_data(path: Path) -> tuple[str, np.ndarray, np.ndarray]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        first = next(reader, None)
        second = next(reader, None)
        if first is None or second is None:
            raise SystemExit(f"Invalid TSV format: {path}")
        gb_name = first[1].strip() if len(first) >= 2 else path.stem
        if len(second) < 2 or second[0] != "level":
            raise SystemExit(f"Expected header row with level/required_points: {path}")

        levels: List[int] = []
        points: List[int] = []
        for row in reader:
            if len(row) < 2:
                continue
            level = parse_int(row[0])
            required_points = parse_int(row[1])
            if level is None or required_points is None:
                continue
            levels.append(level)
            points.append(required_points)

    if not levels:
        raise SystemExit(f"No valid rows found: {path}")

    order = np.argsort(np.array(levels))
    x = np.array(levels, dtype=float)[order]
    y = np.array(points, dtype=float)[order]
    return gb_name, x, y


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - float(np.mean(y_true))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    return r2, rmse, mae


def fit_linear_segment(label: str, x: np.ndarray, y: np.ndarray) -> tuple[SegmentFit, np.ndarray]:
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    r2, rmse, mae = metrics(y, pred)
    fit = SegmentFit(
        label=label,
        min_level=int(np.min(x)),
        max_level=int(np.max(x)),
        n_points=len(x),
        slope=float(slope),
        intercept=float(intercept),
        r2=r2,
        rmse=rmse,
        mae=mae,
    )
    return fit, pred


def full_int_formatter() -> FuncFormatter:
    return FuncFormatter(lambda value, _pos: f"{int(round(value)):,}")


def consecutive_deltas(levels: Sequence[float], values: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    delta_levels: List[float] = []
    delta_values: List[float] = []
    for idx in range(1, len(levels)):
        if int(levels[idx]) - int(levels[idx - 1]) == 1:
            delta_levels.append(levels[idx])
            delta_values.append(values[idx] - values[idx - 1])
    return np.array(delta_levels), np.array(delta_values)


def main() -> None:
    args = parse_args()
    if args.cut1 <= 0:
        raise SystemExit("--cut1 must be > 0")
    if args.cut2 <= args.cut1:
        raise SystemExit("--cut2 must be greater than --cut1")
    if args.zoom_max <= 0:
        raise SystemExit("--zoom-max must be > 0")
    if args.dpi < 120:
        raise SystemExit("--dpi must be >= 120")

    input_path = Path(args.input_tsv).expanduser().resolve()
    gb_name, x, y = load_gb_data(input_path)
    level_min = int(np.min(x))
    level_max = int(np.max(x))
    level_set = {int(v) for v in x}
    missing_levels = [lvl for lvl in range(level_min, level_max + 1) if lvl not in level_set]

    mask1 = x <= args.cut1
    mask2 = (x > args.cut1) & (x <= args.cut2)
    mask3 = x > args.cut2
    masks = [mask1, mask2, mask3]
    labels = [
        f"{level_min} <= level <= {args.cut1}",
        f"{args.cut1 + 1} <= level <= {args.cut2}",
        f"{args.cut2 + 1} <= level <= {level_max}",
    ]

    fits: List[SegmentFit] = []
    combined_pred = np.zeros_like(y)
    for label, mask in zip(labels, masks):
        xs = x[mask]
        ys = y[mask]
        if len(xs) < 2:
            continue
        fit, pred = fit_linear_segment(label, xs, ys)
        fits.append(fit)
        combined_pred[mask] = pred

    overall_r2, overall_rmse, overall_mae = metrics(y, combined_pred)
    residuals = y - combined_pred
    delta_levels, delta_values = consecutive_deltas(x, y)

    out_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else (input_path.parent / "graphs")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(gb_name)
    base = f"{safe_name}_full_report_cut_{args.cut1}_{args.cut2}"
    plot_path = out_dir / f"{base}.png"
    report_path = out_dir / f"{base}.md"
    json_path = out_dir / f"{base}.json"

    fig = plt.figure(figsize=(13.5, 10.5))
    grid = GridSpec(2, 2, figure=fig, height_ratios=[1.2, 1.0], hspace=0.28, wspace=0.22)
    fmt_int = full_int_formatter()
    colors = ["#d62728", "#2ca02c", "#9467bd"]

    ax1 = fig.add_subplot(grid[0, :])
    ax1.scatter(x, y, s=20, color="#1f77b4", alpha=0.72, label="Observed points")
    ax1.plot(x, y, color="#1f77b4", alpha=0.25, linewidth=1.2)
    for fit, color in zip(fits, colors):
        xp = np.linspace(fit.min_level, fit.max_level, 200)
        yp = fit.slope * xp + fit.intercept
        ax1.plot(xp, yp, color=color, linewidth=2.0, label=f"{fit.label} fit")
    ax1.axvspan(level_min, min(args.zoom_max, level_max), color="#ffcc80", alpha=0.18, label="Zoom window")
    ax1.set_title(f"{gb_name}: Overview + Piecewise Fit")
    ax1.set_xlabel("Level")
    ax1.set_ylabel("Required Points")
    ax1.grid(True, linestyle="--", alpha=0.28)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.yaxis.set_major_formatter(fmt_int)
    ax1.yaxis.set_major_locator(MaxNLocator(nbins=8))

    ax2 = fig.add_subplot(grid[1, 0])
    zoom_mask = x <= args.zoom_max
    ax2.scatter(x[zoom_mask], y[zoom_mask], s=22, color="#2ca02c", alpha=0.88, label="Observed")
    ax2.plot(x[zoom_mask], y[zoom_mask], color="#2ca02c", linewidth=1.3, alpha=0.55)
    if fits:
        first_fit = fits[0]
        xp = np.linspace(max(level_min, first_fit.min_level), min(args.zoom_max, first_fit.max_level), 120)
        yp = first_fit.slope * xp + first_fit.intercept
        ax2.plot(xp, yp, color="#d62728", linewidth=2.0, label="Segment-1 fit")
    ax2.set_title(f"Lower-Level Detail ({level_min}..{min(args.zoom_max, level_max)})")
    ax2.set_xlabel("Level")
    ax2.set_ylabel("Required Points")
    ax2.grid(True, linestyle="--", alpha=0.30)
    ax2.legend(loc="upper left", fontsize=8)
    ax2.yaxis.set_major_formatter(fmt_int)
    ax2.yaxis.set_major_locator(MaxNLocator(nbins=7))

    ax3 = fig.add_subplot(grid[1, 1])
    ax3.scatter(delta_levels, delta_values, s=18, color="#ff7f0e", alpha=0.85)
    ax3.plot(delta_levels, delta_values, color="#ff7f0e", alpha=0.55, linewidth=1.1)
    ax3.axhline(0, color="black", linewidth=0.8, alpha=0.6)
    ax3.set_title("Increment Per Level (consecutive levels only)")
    ax3.set_xlabel("Level")
    ax3.set_ylabel("Δ required_points")
    ax3.grid(True, linestyle="--", alpha=0.30)
    ax3.yaxis.set_major_formatter(fmt_int)
    ax3.yaxis.set_major_locator(MaxNLocator(nbins=7))

    fig.suptitle(
        f"{gb_name}: Multi-Scale View + 3-Piece Linear Regression (cuts {args.cut1}, {args.cut2})",
        fontsize=13,
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(plot_path, dpi=args.dpi)

    lines: List[str] = []
    lines.append(f"# {gb_name} Full Analysis Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Source file: `{input_path}`")
    lines.append(f"- Data points: `{len(x)}`")
    lines.append(f"- Level range: `{level_min}..{level_max}`")
    lines.append(f"- Cut points: `{args.cut1}`, `{args.cut2}`")
    lines.append(f"- Zoom window: `{level_min}..{min(args.zoom_max, level_max)}`")
    lines.append("")
    lines.append("## Data Quality")
    lines.append(f"- Missing levels in range: `{len(missing_levels)}`")
    if missing_levels:
        preview = ", ".join(str(v) for v in missing_levels[:20])
        suffix = " ..." if len(missing_levels) > 20 else ""
        lines.append(f"- Missing level examples: `{preview}{suffix}`")
    delta_unique = sorted({int(v) for v in delta_values}) if len(delta_values) else []
    lines.append(f"- Consecutive-level increments observed: `{len(delta_unique)}` unique values")
    if delta_unique:
        inc_preview = ", ".join(str(v) for v in delta_unique[:15])
        inc_suffix = " ..." if len(delta_unique) > 15 else ""
        lines.append(f"- Increment examples: `{inc_preview}{inc_suffix}`")
    lines.append("")
    lines.append("## Piecewise Linear Fit")
    for fit in fits:
        lines.append(f"### Segment `{fit.label}`")
        lines.append(
            f"- Equation: `required_points = {fit.slope:.12f} * level + {fit.intercept:.12f}`"
        )
        lines.append(
            f"- Points: `{fit.n_points}` (`{fit.min_level}..{fit.max_level}`)"
        )
        lines.append(
            f"- Fit quality: `R²={fit.r2:.12f}`, `RMSE={fit.rmse:.6f}`, `MAE={fit.mae:.6f}`"
        )
        lines.append("")
    lines.append("## Combined Fit Quality")
    lines.append(f"- `R²={overall_r2:.12f}`")
    lines.append(f"- `RMSE={overall_rmse:.6f}`")
    lines.append(f"- `MAE={overall_mae:.6f}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("- The combined figure overlays the 3-piece regression on the full trend.")
    lines.append("- The lower-level zoom isolates early progression where absolute values are much smaller.")
    lines.append("- The increment panel highlights local step-size changes and discontinuities.")
    lines.append("- Missing levels indicate sparse sampling at higher levels in this dataset.")
    lines.append("")
    lines.append(f"![{gb_name} combined analysis]({plot_path.name})")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    payload = {
        "gb_name": gb_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": str(input_path),
        "cuts": [args.cut1, args.cut2],
        "zoom_max": args.zoom_max,
        "point_count": len(x),
        "level_range": [level_min, level_max],
        "missing_levels_count": len(missing_levels),
        "missing_levels": missing_levels,
        "overall_metrics": {
            "r2": overall_r2,
            "rmse": overall_rmse,
            "mae": overall_mae,
        },
        "segment_fits": [
            {
                "label": fit.label,
                "n_points": fit.n_points,
                "min_level": fit.min_level,
                "max_level": fit.max_level,
                "slope": fit.slope,
                "intercept": fit.intercept,
                "r2": fit.r2,
                "rmse": fit.rmse,
                "mae": fit.mae,
            }
            for fit in fits
        ],
        "outputs": {
            "plot": str(plot_path),
            "report_markdown": str(report_path),
            "metrics_json": str(json_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Plot: {plot_path}")
    print(f"Report: {report_path}")
    print(f"Metrics JSON: {json_path}")


if __name__ == "__main__":
    main()
