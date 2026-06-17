#!/usr/bin/env python3
"""Build per-GB unique requiredPoints reports from ranking crawl TSV chunks."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, List

from gb_search_query import OUTPUT_DIR, sanitize_filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one report per GB with unique requiredPoints variants per level."
    )
    parser.add_argument(
        "--input-dir",
        default=str(OUTPUT_DIR / "beta_gb_player_ranking"),
        help="Directory containing chunk TSV files (default: output/beta_gb_player_ranking).",
    )
    parser.add_argument(
        "--input-glob",
        default="gb_ranking_pages_*.tsv",
        help="Glob pattern for input TSV chunks (default: gb_ranking_pages_*.tsv).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory for per-GB reports (default: <input-dir>/gb_required_points_reports).",
    )
    parser.add_argument(
        "--summary-file",
        default="",
        help="Optional summary TSV path (default: <output-dir>/summary.tsv).",
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


def load_required_points(
    input_files: List[Path],
) -> Dict[str, Dict[int, int]]:
    per_gb: DefaultDict[str, Dict[int, int]] = defaultdict(dict)

    for file_path in input_files:
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                gb_name = (row.get("gb_name") or "").strip()
                if not gb_name:
                    continue
                level = parse_int(row.get("level") or "")
                required_points = parse_int(row.get("requiredPoints") or "")
                if level is None or required_points is None:
                    continue
                # Keep the first value seen for each GB level; skip variant checks.
                if level not in per_gb[gb_name]:
                    per_gb[gb_name][level] = required_points

    normalized: Dict[str, Dict[int, int]] = {}
    for gb_name, level_map in per_gb.items():
        normalized[gb_name] = dict(level_map)
    return normalized


def write_gb_report(output_path: Path, gb_name: str, level_map: Dict[int, int]) -> None:
    levels = sorted(level_map.keys())
    lines = [
        f"gb_name\t{gb_name}",
        "level\trequired_points",
    ]

    for level in levels:
        lines.append(f"{level}\t{level_map[level]}")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_summary(
    output_path: Path,
    input_files: List[Path],
    per_gb: Dict[str, Dict[int, int]],
) -> None:
    lines = [
        f"generated_at\t{datetime.now().isoformat(timespec='seconds')}",
        f"input_files\t{len(input_files)}",
        f"gb_count\t{len(per_gb)}",
        "gb_name\tlevels_found\tmin_level\tmax_level",
    ]

    for gb_name in sorted(per_gb.keys()):
        level_map = per_gb[gb_name]
        levels = sorted(level_map.keys())
        min_level = levels[0] if levels else ""
        max_level = levels[-1] if levels else ""
        lines.append(f"{gb_name}\t{len(levels)}\t{min_level}\t{max_level}")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    input_files = sorted(input_dir.glob(args.input_glob))
    if not input_files:
        raise SystemExit(f"No input files matched: {input_dir / args.input_glob}")

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else (input_dir / "gb_required_points_reports")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    per_gb = load_required_points(input_files)
    if not per_gb:
        raise SystemExit("No valid rows found in input TSV files.")

    for gb_name in sorted(per_gb.keys()):
        safe_name = sanitize_filename(gb_name)
        report_path = output_dir / f"{safe_name}.tsv"
        write_gb_report(report_path, gb_name, per_gb[gb_name])

    summary_path = (
        Path(args.summary_file).expanduser().resolve()
        if args.summary_file
        else (output_dir / "summary.tsv")
    )
    write_summary(summary_path, input_files, per_gb)

    print(f"Input directory: {input_dir}")
    print(f"Input files: {len(input_files)}")
    print(f"GB reports: {len(per_gb)}")
    print(f"Output directory: {output_dir}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
