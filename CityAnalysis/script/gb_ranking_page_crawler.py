#!/usr/bin/env python3
"""Crawl Great Building ranking pages and export page/name/level/requiredPoints."""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError

from gb_search_query import (
    OUTPUT_DIR,
    build_cookie_header,
    build_get_ranking_request,
    describe_response_issue,
    extract_response_data,
    send_requests,
)

ROWS_PER_PAGE = 10
ROWS_PER_GROUP = 50
PAGES_PER_GROUP = ROWS_PER_GROUP // ROWS_PER_PAGE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect GB ranking rows one UI page at a time with throttled getRanking calls."
    )
    parser.add_argument("--world", default="zz1", help="World host prefix (default: zz1)")
    parser.add_argument("--h", required=True, help="Gateway h value from /game/json?h=...")
    parser.add_argument("--sid", required=True, help="Session cookie sid")
    parser.add_argument("--cid", required=True, help="Session cookie cid")
    parser.add_argument(
        "--ranking-category",
        default="great_building",
        help="RankingCategory enum value (default: great_building)",
    )
    parser.add_argument(
        "--era",
        default=None,
        help="Optional era filter token (JSON null when omitted)",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First UI page to process (1-based, default: 1).",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=0,
        help="Last UI page to process (0 = auto from response length).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between network requests in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=5,
        help="Retry count for failed getRanking requests (default: 5).",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=2.0,
        help="Initial retry delay in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=1.5,
        help="Retry delay multiplier (default: 1.5).",
    )
    parser.add_argument(
        "--request-id",
        type=int,
        default=0,
        help="Request ID seed. Default: current epoch seconds.",
    )
    parser.add_argument(
        "--version",
        default="auto",
        help="Client version for Client-Identification (default: auto, discovered from live ForgeHX bundle).",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds (default: 30).")
    parser.add_argument(
        "--extra-cookies",
        default="",
        help="Optional extra cookies string, e.g. 'foo=bar; baz=1'",
    )
    parser.add_argument(
        "--output-tsv",
        default="",
        help="Output TSV path. Default: output/gb_ranking_pages_<timestamp>.tsv",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory for chunked files (used with --pages-per-file).",
    )
    parser.add_argument(
        "--pages-per-file",
        type=int,
        default=0,
        help="Split output into one TSV per N pages (0 = single file, default: 0).",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Checkpoint JSON path. Default: <output>.checkpoint.json",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint file.",
    )
    parser.add_argument(
        "--print-every-pages",
        type=int,
        default=100,
        help="Progress print interval by UI pages (default: 100).",
    )
    return parser.parse_args()


def resolve_output_path(output_arg: str) -> Path:
    if output_arg:
        return Path(output_arg).expanduser().resolve()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return OUTPUT_DIR / f"gb_ranking_pages_{stamp}.tsv"


def resolve_checkpoint_path(checkpoint_arg: str, output_path: Path) -> Path:
    if checkpoint_arg:
        return Path(checkpoint_arg).expanduser().resolve()
    return output_path.with_suffix(output_path.suffix + ".checkpoint.json")


def resolve_checkpoint_path_for_dir(checkpoint_arg: str, output_dir: Path) -> Path:
    if checkpoint_arg:
        return Path(checkpoint_arg).expanduser().resolve()
    return output_dir / "crawl.checkpoint.json"


def load_checkpoint(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid checkpoint JSON: {path} ({exc})") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"Invalid checkpoint payload shape: {path}")
    return raw


def write_checkpoint(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_page_group(
    *,
    world: str,
    h_value: str,
    cookie_header: str,
    version: str,
    timeout: float,
    ranking_category: str,
    era: Optional[str],
    page_group: int,
    request_id: int,
    retry_count: int,
    retry_delay_seconds: float,
    retry_backoff: float,
) -> Dict[str, Any]:
    attempt = 0
    while True:
        try:
            payload = send_requests(
                world=world,
                h_value=h_value,
                requests=[
                    build_get_ranking_request(
                        ranking_category=ranking_category,
                        era=era,
                        page_group=page_group,
                        request_id=request_id,
                    )
                ],
                cookie_header=cookie_header,
                version=version,
                timeout=timeout,
            )
            response_data = extract_response_data(payload, "RankingService", "getRanking")
            if response_data is None:
                detail = describe_response_issue(payload)
                if detail:
                    raise RuntimeError(f"RankingService.getRanking failed: {detail}")
                raise RuntimeError("RankingService.getRanking response not found")
            if isinstance(response_data, list):
                return {
                    "rankings": response_data,
                    "page": page_group,
                    "length": len(response_data),
                }
            if not isinstance(response_data, dict):
                raise RuntimeError(
                    f"RankingService.getRanking returned unexpected payload type: {type(response_data).__name__}"
                )

            if response_data.get("__class__") == "Error":
                title = str(response_data.get("title", "")).strip()
                message = str(response_data.get("message", "")).strip()
                detail = " ".join(part for part in [title, message] if part) or "Unknown error"
                raise RuntimeError(f"RankingService.getRanking failed: {detail}")

            return response_data

        except (HTTPError, URLError, RuntimeError) as exc:
            if attempt >= retry_count:
                raise SystemExit(
                    f"Failed page_group={page_group} after {retry_count + 1} attempts: {exc}"
                ) from exc
            wait_seconds = retry_delay_seconds * (retry_backoff ** attempt)
            print(
                f"[warn] page_group={page_group} attempt={attempt + 1}/{retry_count + 1} failed: {exc} "
                f"| retry in {wait_seconds:.2f}s"
            )
            time.sleep(wait_seconds)
            attempt += 1


def page_slice_bounds(page_number: int) -> tuple[int, int]:
    index_in_group = (page_number - 1) % PAGES_PER_GROUP
    start = index_in_group * ROWS_PER_PAGE
    end = start + ROWS_PER_PAGE
    return start, end


def chunk_file_path(output_dir: Path, page_number: int, pages_per_file: int, total_pages: int) -> Path:
    chunk_start = ((page_number - 1) // pages_per_file) * pages_per_file + 1
    chunk_end = min(chunk_start + pages_per_file - 1, total_pages)
    filename = f"gb_ranking_pages_{chunk_start:05d}_{chunk_end:05d}.tsv"
    return output_dir / filename


def main() -> None:
    args = parse_args()
    if args.start_page < 1:
        raise SystemExit("--start-page must be >= 1")
    if args.end_page < 0:
        raise SystemExit("--end-page must be >= 0")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds must be >= 0")
    if args.retry_count < 0:
        raise SystemExit("--retry-count must be >= 0")
    if args.retry_delay_seconds < 0:
        raise SystemExit("--retry-delay-seconds must be >= 0")
    if args.retry_backoff < 1:
        raise SystemExit("--retry-backoff must be >= 1")
    if args.pages_per_file < 0:
        raise SystemExit("--pages-per-file must be >= 0")

    base_request_id = args.request_id if args.request_id > 0 else int(time.time())
    cookie_header = build_cookie_header(args.sid, args.cid, args.extra_cookies)

    chunk_mode = args.pages_per_file > 0
    output_dir: Optional[Path] = None
    output_path: Optional[Path] = None
    if chunk_mode:
        if args.output_tsv:
            raise SystemExit("--output-tsv cannot be used together with --pages-per-file")
        output_dir = (
            Path(args.output_dir).expanduser().resolve()
            if args.output_dir
            else (OUTPUT_DIR / "beta_gb_player_ranking").resolve()
        )
        checkpoint_path = resolve_checkpoint_path_for_dir(args.checkpoint, output_dir)
    else:
        output_path = resolve_output_path(args.output_tsv)
        checkpoint_path = resolve_checkpoint_path(args.checkpoint, output_path)

    checkpoint = load_checkpoint(checkpoint_path) if args.resume else None
    if args.resume and checkpoint is None:
        raise SystemExit(f"Checkpoint not found for --resume: {checkpoint_path}")

    start_page = args.start_page
    request_id = base_request_id
    resuming = checkpoint is not None
    if checkpoint is not None:
        cp_next_page = checkpoint.get("nextPage")
        cp_request_id = checkpoint.get("nextRequestId")
        cp_completed = checkpoint.get("completed")
        cp_pages_per_file = checkpoint.get("pagesPerFile")
        cp_output_dir = checkpoint.get("outputDir")
        cp_output = checkpoint.get("outputPath")

        if isinstance(cp_pages_per_file, int) and cp_pages_per_file != args.pages_per_file:
            raise SystemExit(
                f"Checkpoint pagesPerFile={cp_pages_per_file} does not match --pages-per-file={args.pages_per_file}"
            )

        if chunk_mode:
            if isinstance(cp_output_dir, str) and cp_output_dir:
                output_dir = Path(cp_output_dir).expanduser().resolve()
        else:
            if isinstance(cp_output, str) and cp_output:
                output_path = Path(cp_output).expanduser().resolve()

        if cp_completed is True:
            raise SystemExit(f"Checkpoint already marked completed: {checkpoint_path}")
        if isinstance(cp_next_page, int) and cp_next_page >= 1:
            start_page = cp_next_page
        if isinstance(cp_request_id, int) and cp_request_id > request_id:
            request_id = cp_request_id

    if output_path is not None and resuming and not output_path.exists():
        raise SystemExit(f"Output file from checkpoint is missing: {output_path}")

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    first_group = (start_page - 1) // PAGES_PER_GROUP
    first_group_data = fetch_page_group(
        world=args.world,
        h_value=args.h,
        cookie_header=cookie_header,
        version=args.version,
        timeout=args.timeout,
        ranking_category=args.ranking_category,
        era=args.era,
        page_group=first_group,
        request_id=request_id,
        retry_count=args.retry_count,
        retry_delay_seconds=args.retry_delay_seconds,
        retry_backoff=args.retry_backoff,
    )
    request_id += 1

    total_length_value = first_group_data.get("length")
    total_length = total_length_value if isinstance(total_length_value, int) else 0
    total_pages = max(1, math.ceil(total_length / ROWS_PER_PAGE)) if total_length else 1
    end_page = total_pages if args.end_page == 0 else min(args.end_page, total_pages)
    if start_page > end_page:
        raise SystemExit(f"Nothing to do: start_page={start_page} > end_page={end_page}")

    current_handle = None
    current_writer = None
    current_output_path: Optional[Path] = None
    current_group = first_group
    current_group_data = first_group_data
    pages_done = 0
    request_count = 1

    try:
        for page_number in range(start_page, end_page + 1):
            target_group = (page_number - 1) // PAGES_PER_GROUP
            if target_group != current_group:
                if args.delay_seconds > 0:
                    time.sleep(args.delay_seconds)
                current_group_data = fetch_page_group(
                    world=args.world,
                    h_value=args.h,
                    cookie_header=cookie_header,
                    version=args.version,
                    timeout=args.timeout,
                    ranking_category=args.ranking_category,
                    era=args.era,
                    page_group=target_group,
                    request_id=request_id,
                    retry_count=args.retry_count,
                    retry_delay_seconds=args.retry_delay_seconds,
                    retry_backoff=args.retry_backoff,
                )
                request_id += 1
                request_count += 1
                current_group = target_group

            if chunk_mode:
                assert output_dir is not None
                page_output_path = chunk_file_path(output_dir, page_number, args.pages_per_file, total_pages)
            else:
                assert output_path is not None
                page_output_path = output_path

            if current_output_path != page_output_path:
                if current_handle is not None:
                    current_handle.close()

                file_exists = page_output_path.exists()
                chunk_start_page = ((page_number - 1) // max(1, args.pages_per_file)) * max(1, args.pages_per_file) + 1
                should_append = (
                    file_exists
                    and (
                        (not chunk_mode and resuming)
                        or (chunk_mode and resuming and page_number != chunk_start_page)
                    )
                )
                mode = "a" if should_append else "w"
                current_handle = page_output_path.open(mode, encoding="utf-8", newline="")
                current_writer = csv.writer(current_handle, delimiter="\t")
                if mode == "w":
                    current_writer.writerow(["page", "rank", "gb_name", "level", "requiredPoints"])
                current_output_path = page_output_path

            assert current_writer is not None
            assert current_handle is not None

            rankings = current_group_data.get("rankings")
            rows = rankings if isinstance(rankings, list) else []
            slice_start, slice_end = page_slice_bounds(page_number)
            page_rows = rows[slice_start:slice_end]

            if not page_rows:
                break

            for row in page_rows:
                if not isinstance(row, dict):
                    continue
                current_writer.writerow(
                    [
                        page_number,
                        row.get("rank", ""),
                        row.get("name", ""),
                        row.get("level", ""),
                        row.get("requiredPoints", ""),
                    ]
                )

            current_handle.flush()
            pages_done += 1
            next_page = page_number + 1
            checkpoint_payload: Dict[str, Any] = {
                "completed": False,
                "world": args.world,
                "rankingCategory": args.ranking_category,
                "era": args.era,
                "pagesPerFile": args.pages_per_file,
                "checkpointUpdatedAt": datetime.now().isoformat(timespec="seconds"),
                "totalLength": total_length,
                "totalPages": total_pages,
                "nextPage": next_page,
                "nextRequestId": request_id,
            }
            if chunk_mode:
                assert output_dir is not None
                checkpoint_payload["outputDir"] = str(output_dir)
            else:
                assert output_path is not None
                checkpoint_payload["outputPath"] = str(output_path)
            write_checkpoint(checkpoint_path, checkpoint_payload)

            if args.print_every_pages > 0 and (
                pages_done == 1 or pages_done % args.print_every_pages == 0 or page_number == end_page
            ):
                location = output_dir if chunk_mode else output_path
                print(
                    f"Progress: page {page_number}/{end_page} | "
                    f"requests={request_count} | output={location}"
                )
    finally:
        if current_handle is not None:
            current_handle.close()

    final_payload: Dict[str, Any] = {
        "completed": True,
        "world": args.world,
        "rankingCategory": args.ranking_category,
        "era": args.era,
        "pagesPerFile": args.pages_per_file,
        "checkpointUpdatedAt": datetime.now().isoformat(timespec="seconds"),
        "totalLength": total_length,
        "totalPages": total_pages,
        "nextPage": end_page + 1,
        "nextRequestId": request_id,
    }
    if chunk_mode:
        assert output_dir is not None
        final_payload["outputDir"] = str(output_dir)
    else:
        assert output_path is not None
        final_payload["outputPath"] = str(output_path)
    write_checkpoint(checkpoint_path, final_payload)

    print(f"Ranking category: {args.ranking_category}")
    print(f"Total rows reported by server: {total_length}")
    print(f"Pages written: {start_page}..{end_page} ({end_page - start_page + 1} pages)")
    if chunk_mode:
        assert output_dir is not None
        print(f"Output directory: {output_dir}")
    else:
        assert output_path is not None
        print(f"TSV: {output_path}")
    print(f"Checkpoint: {checkpoint_path}")


if __name__ == "__main__":
    main()
