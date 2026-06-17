#!/usr/bin/env python3
"""Scan first N GB ranking pages and list players whose The Arc level is at/above a threshold."""
from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from gb_search_query import (
    OUTPUT_DIR,
    build_cookie_header,
    build_get_ranking_request,
    describe_response_issue,
    extract_response_data,
    send_requests,
)

PAGES_PER_GROUP = 5
ROWS_PER_PAGE = 10
DEFAULT_OUTPUT_SUBDIR = "us24_arc_rank_scan"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan first ranking pages and find players with The Arc level >= threshold."
    )
    parser.add_argument(
        "--url",
        default="https://us24.forgeofempires.com/game/json?h=bIxHw5iPyeSxtQnFvbXby5so",
        help="FOE game/json URL including ?h=... (default: us24 URL provided).",
    )
    parser.add_argument(
        "--sid",
        default=os.environ.get("FOE_SID", "Ls7pM1uq5yQVge9WLokGKX0nFXQ2_Q1C6_RuUyrD"),
        help="Session cookie sid. Default: FOE_SID env var or current embedded us24 session value.",
    )
    parser.add_argument(
        "--cid",
        default=os.environ.get("FOE_CID", "1705220684"),
        help="Session cookie cid. Default: FOE_CID env var or current embedded us24 session value.",
    )
    parser.add_argument(
        "--ranking-category",
        default="great_building",
        help="RankingCategory enum value (default: great_building).",
    )
    parser.add_argument(
        "--target-gb-name",
        default="The Arc",
        help='Target GB display name (default: "The Arc").',
    )
    parser.add_argument(
        "--min-level",
        type=int,
        default=180,
        help="Minimum Arc level to keep (default: 180).",
    )
    parser.add_argument(
        "--first-pages",
        type=int,
        default=50,
        help="Number of top UI pages to scan (default: 50).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Delay between network calls in seconds (default: 0.5).",
    )
    parser.add_argument("--request-id", type=int, default=0, help="Request ID seed. Default: current epoch seconds.")
    parser.add_argument(
        "--version",
        default="auto",
        help="Client version (default: auto, discovered from live ForgeHX bundle).",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds (default: 30).")
    parser.add_argument(
        "--extra-cookies",
        default="",
        help="Optional extra cookie string, e.g. 'foo=bar; baz=1'.",
    )
    parser.add_argument(
        "--output-tsv",
        default="",
        help="Optional output TSV path. Default: output/us24_arc_level_scan_<timestamp>.tsv",
    )
    return parser.parse_args()


def parse_world_and_h(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit(f"Invalid URL scheme in --url: {url}")
    host = parsed.hostname or ""
    if not host:
        raise SystemExit(f"Could not parse host from --url: {url}")
    world = host.split(".")[0]
    params = parse_qs(parsed.query)
    h_values = params.get("h", [])
    if not h_values or not h_values[0]:
        raise SystemExit("Missing ?h=... in --url")
    return world, h_values[0]


def write_tsv(path_arg: str, rows: List[Dict[str, Any]], default_filename: str) -> Path:
    if path_arg:
        output_path = Path(path_arg).expanduser().resolve()
    else:
        output_path = (OUTPUT_DIR / DEFAULT_OUTPUT_SUBDIR / default_filename).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["page", "rank", "player_name", "guild_name", "arc_level", "requiredPoints"])
        for row in rows:
            writer.writerow(
                [
                    row.get("page", ""),
                    row.get("rank", ""),
                    row.get("player_name", ""),
                    row.get("guild_name", ""),
                    row.get("arc_level", ""),
                    row.get("requiredPoints", ""),
                ]
            )
    return output_path


def main() -> None:
    args = parse_args()
    if not args.sid or not args.cid:
        raise SystemExit("Missing authentication cookies. Provide --sid and --cid (or FOE_SID/FOE_CID env vars).")
    if args.first_pages <= 0:
        raise SystemExit("--first-pages must be > 0")
    if args.min_level <= 0:
        raise SystemExit("--min-level must be > 0")

    world, h_value = parse_world_and_h(args.url)
    cookie_header = build_cookie_header(args.sid, args.cid, args.extra_cookies)
    request_id = args.request_id if args.request_id > 0 else int(time.time())

    page_groups = (args.first_pages + PAGES_PER_GROUP - 1) // PAGES_PER_GROUP
    matches: List[Dict[str, Any]] = []

    for page_group in range(page_groups):
        if page_group > 0 and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

        try:
            payload = send_requests(
                world=world,
                h_value=h_value,
                requests=[
                    build_get_ranking_request(
                        ranking_category=args.ranking_category,
                        era=None,
                        page_group=page_group,
                        request_id=request_id,
                    )
                ],
                cookie_header=cookie_header,
                version=args.version,
                timeout=args.timeout,
            )
        except HTTPError as exc:
            raise SystemExit(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise SystemExit(f"Network error: {exc.reason}") from exc

        request_id += 1
        page_data = extract_response_data(payload, "RankingService", "getRanking")
        if page_data is None:
            detail = describe_response_issue(payload) or "RankingService.getRanking response not found"
            raise SystemExit(f"RankingService.getRanking failed: {detail}")

        if isinstance(page_data, dict):
            if page_data.get("__class__") == "Error":
                title = str(page_data.get("title", "")).strip()
                message = str(page_data.get("message", "")).strip()
                detail = " ".join(part for part in [title, message] if part) or "Unknown error"
                raise SystemExit(f"RankingService.getRanking failed: {detail}")
            rankings = page_data.get("rankings")
            rows = rankings if isinstance(rankings, list) else []
        elif isinstance(page_data, list):
            # Some responses use responseData as direct ranking rows.
            rows = page_data
        else:
            raise SystemExit(
                f"RankingService.getRanking failed: unexpected responseData type {type(page_data).__name__}"
            )

        for in_group_page in range(PAGES_PER_GROUP):
            ui_page = page_group * PAGES_PER_GROUP + in_group_page + 1
            if ui_page > args.first_pages:
                break
            start = in_group_page * ROWS_PER_PAGE
            end = start + ROWS_PER_PAGE
            page_rows = rows[start:end]
            for row in page_rows:
                if not isinstance(row, dict):
                    continue
                if row.get("name") != args.target_gb_name:
                    continue
                level = row.get("level")
                if not isinstance(level, int) or level < args.min_level:
                    continue
                player = row.get("player") if isinstance(row.get("player"), dict) else {}
                clan = row.get("clan") if isinstance(row.get("clan"), dict) else {}
                player_name = player.get("name")
                if not isinstance(player_name, str) or not player_name.strip():
                    continue
                guild_name_raw = clan.get("name")
                guild_name = guild_name_raw.strip() if isinstance(guild_name_raw, str) else ""
                matches.append(
                    {
                        "page": ui_page,
                        "rank": row.get("rank"),
                        "player_name": player_name.strip(),
                        "guild_name": guild_name,
                        "arc_level": level,
                        "requiredPoints": row.get("requiredPoints"),
                    }
                )

    matches.sort(
        key=lambda item: (
            int(item.get("page")) if isinstance(item.get("page"), int) else 10**9,
            int(item.get("rank")) if isinstance(item.get("rank"), int) else 10**9,
            str(item.get("player_name", "")),
        )
    )

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    default_name = f"us24_arc_level_scan_first_{args.first_pages}_pages_{stamp}.tsv"
    output_path = write_tsv(args.output_tsv, matches, default_name)

    print(f"World: {world}")
    print(f"Scanned pages: 1..{args.first_pages} ({page_groups} getRanking calls)")
    print(f"Filter: gb='{args.target_gb_name}', min_level={args.min_level}")
    print(f"Matches: {len(matches)}")
    print(f"TSV: {output_path}")
    print("")
    for idx, row in enumerate(matches[:200], start=1):
        print(
            f"{idx}. page={row.get('page')} rank={row.get('rank')} | "
            f"player={row.get('player_name')} | guild={row.get('guild_name') or '-'} | "
            f"arc_level={row.get('arc_level')}"
        )


if __name__ == "__main__":
    main()
