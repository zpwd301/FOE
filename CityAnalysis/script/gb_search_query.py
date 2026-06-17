#!/usr/bin/env python3
"""Direct GB ranking search/details query against FOE game/json endpoint."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
SIGNATURE_SECRET = "kGieqOaaLpOTbLmppu/YqVtD7SCH/5EJlrMW0MG03/Rx0Ln35/ANbXCZeYwtWsyFdM6oRKpaDdEjktbeIwRKMQ=="
DEFAULT_CLIENT_VERSION = "1.333"
FORGE_HX_PATH_RE = re.compile(r"(https?://[^\"']+|/[^\"']*|)cache/ForgeHX-[^\"']+\.js")
FORGE_HX_SIGNATURE_RE = re.compile(r'_signatureHash\+"([^"]+)"\+a\)')
FORGE_HX_VERSION_RE = re.compile(r'"version=([0-9]+\.[0-9]+)"\s*,\s*"requiredVersion=([0-9]+\.[0-9]+)"')
CLIENT_CONFIG_CACHE: Dict[str, Tuple[str, str]] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Great Building rankings/details directly via game/json")
    parser.add_argument("--world", default="zz1", help="World host prefix (default: zz1)")
    parser.add_argument("--h", required=True, help="Gateway h value from /game/json?h=...")
    parser.add_argument("--sid", required=True, help="Session cookie sid")
    parser.add_argument("--cid", required=True, help="Session cookie cid")
    parser.add_argument("--query", required=True, help="Search text (player/clan/GB depending on search category)")
    parser.add_argument(
        "--search-category",
        default="player",
        help="Ranking search category parameter (common: player, guild). Default: player",
    )
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
        "--exact",
        action="store_true",
        default=True,
        help="Use exact search mode (default: true)",
    )
    parser.add_argument(
        "--not-exact",
        dest="exact",
        action="store_false",
        help="Disable exact search mode",
    )
    parser.add_argument(
        "--request-id",
        type=int,
        default=0,
        help="Request ID. Default: current epoch seconds (recommended for active browser sessions).",
    )
    parser.add_argument(
        "--version",
        default="auto",
        help="Client version for Client-Identification (default: auto, discovered from live ForgeHX bundle).",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument("--limit", type=int, default=25, help="Rows to print in terminal (default: 25)")
    parser.add_argument(
        "--extra-cookies",
        default="",
        help="Optional extra cookies string, e.g. 'foo=bar; baz=1'",
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="Optional path to save full RankingService.searchRanking response JSON",
    )
    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help=(
            "After searchRanking, fetch selected GB details using: "
            "getOtherPlayerVO, getOtherPlayerOverview, getOtherPlayerCityMapEntity, getConstruction."
        ),
    )
    parser.add_argument(
        "--detail-index",
        type=int,
        default=1,
        help="1-based row index from ranking results for detail fetch (default: 1).",
    )
    parser.add_argument(
        "--detail-player-id",
        type=int,
        default=None,
        help="Optional explicit player_id for detail fetch (overrides row value).",
    )
    parser.add_argument(
        "--detail-entity-id",
        type=int,
        default=None,
        help="Optional explicit entityId for detail fetch (overrides row value).",
    )
    parser.add_argument(
        "--save-detail-json",
        default="",
        help="Optional path to save detail response bundle JSON.",
    )
    parser.add_argument(
        "--collect-required-points",
        action="store_true",
        help="Sweep paged ranking data (getRanking) and collect level->requiredPoints for a target GB name.",
    )
    parser.add_argument(
        "--target-gb-name",
        default="",
        help="GB name filter for --collect-required-points. Default: --query value.",
    )
    parser.add_argument(
        "--expected-min-level",
        type=int,
        default=1,
        help="Expected minimum level for missing-level checks (default: 1).",
    )
    parser.add_argument(
        "--expected-max-level",
        type=int,
        default=400,
        help="Expected maximum level for missing-level checks (default: 400).",
    )
    parser.add_argument(
        "--max-page-groups",
        type=int,
        default=0,
        help="Max getRanking page groups to scan (0 = scan all available pages).",
    )
    parser.add_argument(
        "--batch-pages",
        type=int,
        default=20,
        help="Number of getRanking pages per request batch for --collect-required-points (default: 20).",
    )
    parser.add_argument(
        "--save-levels-json",
        default="",
        help="Optional output path for collected level->requiredPoints JSON.",
    )
    parser.add_argument(
        "--save-levels-tsv",
        default="",
        help="Optional output path for collected level->requiredPoints TSV.",
    )
    return parser.parse_args()


def build_search_payload(
    ranking_category: str,
    era: Optional[str],
    query: str,
    exact: bool,
    search_category: str,
    request_id: int,
) -> List[Dict[str, Any]]:
    return [
        {
            "__class__": "ServerRequest",
            "requestData": [
                {"__enum__": "RankingCategory", "value": ranking_category},
                era,
                query,
                exact,
                search_category,
            ],
            "requestClass": "RankingService",
            "requestMethod": "searchRanking",
            "requestId": request_id,
        }
    ]


def build_server_request(
    request_class: str,
    request_method: str,
    request_data: Sequence[Any],
    request_id: int,
) -> Dict[str, Any]:
    return {
        "__class__": "ServerRequest",
        "requestData": list(request_data),
        "requestClass": request_class,
        "requestMethod": request_method,
        "requestId": request_id,
    }


def build_get_ranking_request(
    ranking_category: str,
    era: Optional[str],
    page_group: int,
    request_id: int,
) -> Dict[str, Any]:
    return build_server_request(
        request_class="RankingService",
        request_method="getRanking",
        request_data=[
            {"__enum__": "RankingCategory", "value": ranking_category},
            era,
            page_group,
        ],
        request_id=request_id,
    )


def fetch_text(url: str, timeout: float, headers: Optional[Dict[str, str]] = None) -> str:
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept-Encoding": "identity",
    }
    if headers:
        request_headers.update(headers)
    req = Request(
        url=url,
        headers=request_headers,
        method="GET",
    )
    with urlopen(req, timeout=timeout) as response:
        content_encoding = str(response.headers.get("Content-Encoding", "")).lower().strip()
        raw = response.read()
        if content_encoding in {"gzip", "x-gzip"}:
            raw = gzip.decompress(raw)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def discover_client_config(world: str, timeout: float, cookie_header: str = "") -> Tuple[str, str]:
    cached = CLIENT_CONFIG_CACHE.get(world)
    if cached is not None:
        return cached

    index_url = f"https://{world}.forgeofempires.com/game/index?"
    index_headers: Dict[str, str] = {
        "Referer": index_url,
        "Origin": f"https://{world}.forgeofempires.com",
    }
    if cookie_header.strip():
        index_headers["Cookie"] = cookie_header
    index_html = fetch_text(index_url, timeout, headers=index_headers)

    path_match = FORGE_HX_PATH_RE.search(index_html)
    if not path_match:
        raise RuntimeError("ForgeHX bundle path not found in /game/index page")
    bundle_path = path_match.group(0)
    bundle_url = bundle_path if bundle_path.startswith("http") else urljoin(index_url, bundle_path)

    bundle_js = fetch_text(bundle_url, timeout, headers=index_headers)

    secret_match = FORGE_HX_SIGNATURE_RE.search(bundle_js)
    version_match = FORGE_HX_VERSION_RE.search(bundle_js)
    if not secret_match:
        raise RuntimeError("request signature secret not found in ForgeHX bundle")
    if not version_match:
        raise RuntimeError("client version not found in ForgeHX bundle")

    signature_secret = secret_match.group(1)
    version = version_match.group(2)
    config = (signature_secret, version)
    CLIENT_CONFIG_CACHE[world] = config
    return config


def resolve_client_config(
    world: str,
    timeout: float,
    version: str,
    signature_secret: Optional[str],
    cookie_header: str,
) -> Tuple[str, str]:
    requested_version = version.strip()
    if requested_version.lower() == "auto":
        requested_version = ""
    requested_secret = signature_secret.strip() if isinstance(signature_secret, str) else ""

    needs_discovery = not requested_version or not requested_secret
    discovered_secret = ""
    discovered_version = ""
    if needs_discovery:
        try:
            discovered_secret, discovered_version = discover_client_config(
                world=world,
                timeout=timeout,
                cookie_header=cookie_header,
            )
        except (HTTPError, URLError, OSError, RuntimeError):
            discovered_secret, discovered_version = "", ""

    resolved_secret = requested_secret or discovered_secret or SIGNATURE_SECRET
    resolved_version = requested_version or discovered_version or DEFAULT_CLIENT_VERSION
    return resolved_secret, resolved_version


def generate_signature(h_value: str, request_body: str, signature_secret: str) -> str:
    digest = hashlib.md5((h_value + signature_secret + request_body).encode("utf-8")).hexdigest()
    return digest[1:11]


def build_cookie_header(sid: str, cid: str, extra: str) -> str:
    base = [f"sid={sid}", f"cid={cid}"]
    extra = extra.strip()
    if extra:
        base.append(extra)
    return "; ".join(base)


def call_game_json(
    world: str,
    h_value: str,
    request_body: str,
    signature: str,
    cookie_header: str,
    version: str,
    timeout: float,
) -> Any:
    url = f"https://{world}.forgeofempires.com/game/json?h={h_value}"
    headers = {
        "Content-Type": "application/json",
        "Client-Identification": (
            f"version={version}; requiredVersion={version}; "
            "platform=bro; platformType=html5; platformVersion=web"
        ),
        "Signature": signature,
        "Origin": f"https://{world}.forgeofempires.com",
        "Referer": f"https://{world}.forgeofempires.com/game/index?",
        "Cookie": cookie_header,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
    }

    req = Request(url=url, data=request_body.encode("utf-8"), headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def send_requests(
    world: str,
    h_value: str,
    requests: List[Dict[str, Any]],
    cookie_header: str,
    version: str,
    timeout: float,
    signature_secret: Optional[str] = None,
) -> Any:
    resolved_secret, resolved_version = resolve_client_config(
        world=world,
        timeout=timeout,
        version=version,
        signature_secret=signature_secret,
        cookie_header=cookie_header,
    )
    request_body = json.dumps(requests, separators=(",", ":"), ensure_ascii=False)
    signature = generate_signature(h_value, request_body, resolved_secret)
    return call_game_json(
        world=world,
        h_value=h_value,
        request_body=request_body,
        signature=signature,
        cookie_header=cookie_header,
        version=resolved_version,
        timeout=timeout,
    )


def extract_ranking_response(response_payload: Any) -> Dict[str, Any]:
    if not isinstance(response_payload, list):
        raise SystemExit("Unexpected response: expected a JSON array")

    for entry in response_payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("requestClass") == "RankingService" and entry.get("requestMethod") == "searchRanking":
            data = entry.get("responseData")
            if isinstance(data, dict):
                if data.get("__class__") == "Error":
                    title = str(data.get("title", "")).strip()
                    message = str(data.get("message", "")).strip()
                    detail = " ".join(part for part in [title, message] if part)
                    raise SystemExit(f"RankingService.searchRanking failed: {detail or 'Unknown error'}")
                return data

    detail = describe_response_issue(response_payload)
    if detail:
        raise SystemExit(f"RankingService.searchRanking failed: {detail}")
    raise SystemExit("RankingService.searchRanking response not found")


def extract_response_data(response_payload: Any, request_class: str, request_method: str) -> Any:
    if not isinstance(response_payload, list):
        return None
    for entry in response_payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("requestClass") == request_class and entry.get("requestMethod") == request_method:
            return entry.get("responseData")
    return None


def describe_response_issue(response_payload: Any) -> str:
    if not isinstance(response_payload, list):
        return ""
    for entry in response_payload:
        if not isinstance(entry, dict):
            continue

        klass = entry.get("__class__")
        if klass == "Redirect":
            header = str(entry.get("header", "")).strip()
            message = str(entry.get("message", "")).strip()
            url = str(entry.get("url", "")).strip()
            detail = " | ".join(part for part in [header, message] if part) or "Redirect response"
            return f"{detail} (url={url})" if url else detail
        if klass == "Error":
            title = str(entry.get("title", "")).strip()
            message = str(entry.get("message", "")).strip()
            detail = " ".join(part for part in [title, message] if part).strip()
            return detail or "Error response"

        response_data = entry.get("responseData")
        if isinstance(response_data, dict):
            data_class = response_data.get("__class__")
            if data_class == "Error":
                title = str(response_data.get("title", "")).strip()
                message = str(response_data.get("message", "")).strip()
                detail = " ".join(part for part in [title, message] if part).strip()
                return detail or "Error response"
            if data_class == "Redirect":
                header = str(response_data.get("header", "")).strip()
                message = str(response_data.get("message", "")).strip()
                url = str(response_data.get("url", "")).strip()
                detail = " | ".join(part for part in [header, message] if part) or "Redirect response"
                return f"{detail} (url={url})" if url else detail

    return ""


def sanitize_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return safe.strip("_") or "query"


def write_json(path_arg: str, data: Any, default_filename: str) -> Path:
    if path_arg:
        out_path = Path(path_arg).expanduser().resolve()
    else:
        out_path = OUTPUT_DIR / default_filename

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def print_summary(ranking_data: Dict[str, Any], limit: int) -> None:
    rankings = ranking_data.get("rankings")
    if not isinstance(rankings, list):
        rankings = []

    total = ranking_data.get("length")
    if not isinstance(total, int):
        total = len(rankings)

    print(f"Total matches: {total}")
    print(f"Rows in response: {len(rankings)}")
    print("")

    for idx, row in enumerate(rankings[: max(0, limit)], start=1):
        if not isinstance(row, dict):
            continue
        player = row.get("player") if isinstance(row.get("player"), dict) else {}
        print(
            f"{idx}. rank={row.get('rank')} | player={player.get('name')} | "
            f"gb={row.get('name')} ({row.get('cityEntityId')}) | level={row.get('level')} | "
            f"points={row.get('points')} | requiredPoints={row.get('requiredPoints')}"
        )


def resolve_detail_target(
    ranking_data: Dict[str, Any],
    detail_index: int,
    detail_player_id: Optional[int],
    detail_entity_id: Optional[int],
) -> Tuple[int, int, Optional[Dict[str, Any]]]:
    rankings = ranking_data.get("rankings")
    rows = rankings if isinstance(rankings, list) else []
    row: Optional[Dict[str, Any]] = None
    if rows and 1 <= detail_index <= len(rows):
        candidate = rows[detail_index - 1]
        if isinstance(candidate, dict):
            row = candidate

    if detail_player_id is not None:
        player_id = detail_player_id
    else:
        player = row.get("player") if isinstance(row, dict) and isinstance(row.get("player"), dict) else {}
        player_id = player.get("player_id")

    if detail_entity_id is not None:
        entity_id = detail_entity_id
    else:
        entity_id = row.get("entityId") if isinstance(row, dict) else None

    if not isinstance(player_id, int) or not isinstance(entity_id, int):
        raise SystemExit(
            "Could not resolve detail target. Provide --detail-player-id and --detail-entity-id, "
            "or ensure --detail-index points to a valid ranking row."
        )
    return player_id, entity_id, row


def fetch_detail_bundle(
    world: str,
    h_value: str,
    cookie_header: str,
    version: str,
    timeout: float,
    request_id_start: int,
    player_id: int,
    entity_id: int,
) -> Dict[str, Any]:
    responses: Dict[str, Any] = {}
    raw_responses: Dict[str, Any] = {}
    request_id = request_id_start

    call_specs: List[Tuple[str, str, List[Any]]] = [
        ("OtherPlayerService", "getOtherPlayerVO", [player_id]),
        ("GreatBuildingsService", "getOtherPlayerOverview", [player_id]),
        ("OtherPlayerService", "getOtherPlayerCityMapEntity", [entity_id, player_id]),
        ("GreatBuildingsService", "getConstruction", [entity_id, player_id]),
    ]

    for request_class, request_method, request_data in call_specs:
        payload = send_requests(
            world=world,
            h_value=h_value,
            requests=[
                build_server_request(
                    request_class=request_class,
                    request_method=request_method,
                    request_data=request_data,
                    request_id=request_id,
                )
            ],
            cookie_header=cookie_header,
            version=version,
            timeout=timeout,
        )
        key = f"{request_class}.{request_method}"
        responses[key] = extract_response_data(payload, request_class, request_method)
        raw_responses[key] = payload
        if request_class == "GreatBuildingsService" and request_method == "getConstruction":
            responses["CityMapService.updateEntity"] = extract_response_data(payload, "CityMapService", "updateEntity")
        request_id += 1

    return {
        "player_id": player_id,
        "entity_id": entity_id,
        "responses": responses,
        "raw_responses": raw_responses,
    }


def print_bonus_lines(bonuses: Any) -> None:
    if not isinstance(bonuses, list) or not bonuses:
        return
    print("Current bonuses:")
    for bonus in bonuses:
        if not isinstance(bonus, dict):
            continue
        target = bonus.get("targetedFeature")
        suffix = f" | targetedFeature={target}" if target else ""
        print(f"- {bonus.get('type')}: {bonus.get('value')}{suffix}")


def print_detail_summary(detail_bundle: Dict[str, Any], selected_row: Optional[Dict[str, Any]]) -> None:
    responses = detail_bundle.get("responses") if isinstance(detail_bundle.get("responses"), dict) else {}
    player_vo = responses.get("OtherPlayerService.getOtherPlayerVO")
    city_entity = responses.get("OtherPlayerService.getOtherPlayerCityMapEntity")
    overview = responses.get("GreatBuildingsService.getOtherPlayerOverview")
    construction = responses.get("GreatBuildingsService.getConstruction")

    print("")
    print("Detail fetch:")
    print(f"player_id={detail_bundle.get('player_id')} | entity_id={detail_bundle.get('entity_id')}")
    if isinstance(selected_row, dict):
        print(
            "selected ranking row: "
            f"rank={selected_row.get('rank')} | gb={selected_row.get('name')} | level={selected_row.get('level')}"
        )

    if isinstance(player_vo, dict) and player_vo.get("__class__") == "Error":
        print(f"getOtherPlayerVO error: {player_vo.get('message')}")
        player_vo = None

    if isinstance(player_vo, dict):
        print(
            f"player: {player_vo.get('name')} | era={player_vo.get('era')} | "
            f"city={player_vo.get('city_name')}"
        )

    if isinstance(overview, dict) and overview.get("__class__") == "Error":
        print(f"getOtherPlayerOverview error: {overview.get('message')}")
        overview = None

    if isinstance(overview, list):
        print(f"other player overview rows: {len(overview)}")

    if isinstance(city_entity, dict) and city_entity.get("__class__") == "Error":
        print(f"getOtherPlayerCityMapEntity error: {city_entity.get('message')}")
        city_entity = None

    if isinstance(city_entity, dict):
        state = city_entity.get("state") if isinstance(city_entity.get("state"), dict) else {}
        print(
            "city entity: "
            f"id={city_entity.get('id')} | cityentity_id={city_entity.get('cityentity_id')} | "
            f"level={city_entity.get('level')}/{city_entity.get('max_level')} | "
            f"invested={state.get('invested_forge_points')} | "
            f"for_level_up={state.get('forge_points_for_level_up')}"
        )
        print_bonus_lines(city_entity.get("bonuses"))

    if isinstance(construction, dict) and construction.get("__class__") == "Error":
        print(f"getConstruction error: {construction.get('message')}")
        construction = None

    if isinstance(construction, dict):
        next_level = construction.get("nextLevelBonuses")
        rankings = construction.get("rankings")
        print(
            "construction: "
            f"ownerEra={construction.get('ownerEra')} | "
            f"nextLevelBonuses={len(next_level) if isinstance(next_level, list) else 0} | "
            f"rankings={len(rankings) if isinstance(rankings, list) else 0}"
        )


def collect_required_points_from_ranking(
    world: str,
    h_value: str,
    cookie_header: str,
    version: str,
    timeout: float,
    ranking_category: str,
    era: Optional[str],
    request_id_start: int,
    target_gb_name: str,
    max_page_groups: int,
    batch_pages: int,
    expected_min_level: int,
    expected_max_level: int,
) -> Dict[str, Any]:
    if batch_pages <= 0:
        raise SystemExit("--batch-pages must be >= 1")

    request_id = request_id_start
    first_payload = send_requests(
        world=world,
        h_value=h_value,
        requests=[
            build_get_ranking_request(
                ranking_category=ranking_category,
                era=era,
                page_group=0,
                request_id=request_id,
            )
        ],
        cookie_header=cookie_header,
        version=version,
        timeout=timeout,
    )
    request_id += 1

    first_data = extract_response_data(first_payload, "RankingService", "getRanking")
    if not isinstance(first_data, dict):
        detail = describe_response_issue(first_payload)
        if detail:
            raise SystemExit(f"RankingService.getRanking failed: {detail}")
        raise SystemExit("RankingService.getRanking did not return an object")
    if first_data.get("__class__") == "Error":
        title = str(first_data.get("title", "")).strip()
        message = str(first_data.get("message", "")).strip()
        detail = " ".join(part for part in [title, message] if part)
        raise SystemExit(f"RankingService.getRanking failed: {detail or 'Unknown error'}")

    total_length_value = first_data.get("length")
    total_length = total_length_value if isinstance(total_length_value, int) else 0
    total_page_groups = max(1, math.ceil(total_length / 50)) if total_length else 1
    page_groups_to_scan = total_page_groups if max_page_groups <= 0 else min(total_page_groups, max_page_groups)

    level_map: Dict[int, set[int]] = {}
    sample_rows: List[Dict[str, Any]] = []

    def process_ranking_page(page_data: Dict[str, Any]) -> None:
        rankings = page_data.get("rankings")
        rows = rankings if isinstance(rankings, list) else []
        page_value = page_data.get("page")
        page_group = page_value if isinstance(page_value, int) else 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("name") != target_gb_name:
                continue
            level = row.get("level")
            required_points = row.get("requiredPoints")
            if not isinstance(level, int) or not isinstance(required_points, int):
                continue
            if level not in level_map:
                level_map[level] = set()
            level_map[level].add(required_points)
            if len(sample_rows) < 200:
                player = row.get("player") if isinstance(row.get("player"), dict) else {}
                sample_rows.append(
                    {
                        "page_group": page_group,
                        "rank": row.get("rank"),
                        "level": level,
                        "requiredPoints": required_points,
                        "player": player.get("name"),
                    }
                )

    process_ranking_page(first_data)

    for start in range(1, page_groups_to_scan, batch_pages):
        end = min(start + batch_pages, page_groups_to_scan)
        requests: List[Dict[str, Any]] = []
        for page_group in range(start, end):
            requests.append(
                build_get_ranking_request(
                    ranking_category=ranking_category,
                    era=era,
                    page_group=page_group,
                    request_id=request_id,
                )
            )
            request_id += 1

        payload = send_requests(
            world=world,
            h_value=h_value,
            requests=requests,
            cookie_header=cookie_header,
            version=version,
            timeout=timeout,
        )

        if not isinstance(payload, list):
            continue
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if entry.get("requestClass") != "RankingService" or entry.get("requestMethod") != "getRanking":
                continue
            page_data = entry.get("responseData")
            if isinstance(page_data, dict) and page_data.get("__class__") == "Error":
                continue
            if isinstance(page_data, dict):
                process_ranking_page(page_data)

    levels_sorted = sorted(level_map.keys())
    missing_expected_levels: List[int] = []
    if expected_min_level <= expected_max_level:
        missing_expected_levels = [
            level for level in range(expected_min_level, expected_max_level + 1) if level not in level_map
        ]

    level_rows = [
        {"level": level, "requiredPointsVariants": sorted(level_map[level])}
        for level in levels_sorted
    ]
    return {
        "targetGbName": target_gb_name,
        "sourceMethod": "RankingService.getRanking",
        "totalLength": total_length,
        "totalPageGroups": total_page_groups,
        "scannedPageGroups": page_groups_to_scan,
        "levelsFoundCount": len(levels_sorted),
        "minLevelFound": levels_sorted[0] if levels_sorted else None,
        "maxLevelFound": levels_sorted[-1] if levels_sorted else None,
        "levels": level_rows,
        "missingExpectedLevels": missing_expected_levels,
        "sampleRows": sample_rows,
    }


def write_required_points_tsv(path_arg: str, data: Dict[str, Any], default_filename: str) -> Path:
    if path_arg:
        out_path = Path(path_arg).expanduser().resolve()
    else:
        out_path = OUTPUT_DIR / default_filename

    levels = data.get("levels")
    rows = levels if isinstance(levels, list) else []

    lines = ["level\trequired_points\tvariants"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        level = row.get("level")
        variants = row.get("requiredPointsVariants")
        if not isinstance(level, int) or not isinstance(variants, list) or not variants:
            continue
        int_variants = [value for value in variants if isinstance(value, int)]
        if not int_variants:
            continue
        int_variants.sort()
        lines.append(f"{level}\t{int_variants[0]}\t{','.join(str(value) for value in int_variants)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    args = parse_args()
    base_request_id = args.request_id if args.request_id > 0 else int(datetime.now().timestamp())
    cookie_header = build_cookie_header(args.sid, args.cid, args.extra_cookies)

    if args.collect_required_points:
        target_name = args.target_gb_name.strip() or args.query
        try:
            collection = collect_required_points_from_ranking(
                world=args.world,
                h_value=args.h,
                cookie_header=cookie_header,
                version=args.version,
                timeout=args.timeout,
                ranking_category=args.ranking_category,
                era=args.era,
                request_id_start=base_request_id,
                target_gb_name=target_name,
                max_page_groups=args.max_page_groups,
                batch_pages=args.batch_pages,
                expected_min_level=args.expected_min_level,
                expected_max_level=args.expected_max_level,
            )
        except HTTPError as exc:
            raise SystemExit(f"HTTP error {exc.code} (collect mode): {exc.reason}") from exc
        except URLError as exc:
            raise SystemExit(f"Network error (collect mode): {exc.reason}") from exc

        print(f"Target GB: {collection.get('targetGbName')}")
        print(f"Source: {collection.get('sourceMethod')}")
        print(
            f"Scanned page groups: {collection.get('scannedPageGroups')} / {collection.get('totalPageGroups')} "
            f"(totalLength={collection.get('totalLength')})"
        )
        print(
            f"Levels found: {collection.get('levelsFoundCount')} | "
            f"range={collection.get('minLevelFound')}..{collection.get('maxLevelFound')}"
        )
        missing = collection.get("missingExpectedLevels")
        missing_list = missing if isinstance(missing, list) else []
        print(f"Missing expected levels: {len(missing_list)}")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_name = f"{sanitize_filename(target_name)}_required_points_from_ranking_{timestamp}.json"
        tsv_name = f"{sanitize_filename(target_name)}_required_points_from_ranking_{timestamp}.tsv"
        json_path = write_json(args.save_levels_json, collection, json_name)
        tsv_path = write_required_points_tsv(args.save_levels_tsv, collection, tsv_name)
        print(f"Saved levels JSON: {json_path}")
        print(f"Saved levels TSV: {tsv_path}")
        return

    search_payload = build_search_payload(
        ranking_category=args.ranking_category,
        era=args.era,
        query=args.query,
        exact=args.exact,
        search_category=args.search_category,
        request_id=base_request_id,
    )

    try:
        response_payload = send_requests(
            world=args.world,
            h_value=args.h,
            requests=search_payload,
            cookie_header=cookie_header,
            version=args.version,
            timeout=args.timeout,
        )
    except HTTPError as exc:
        raise SystemExit(f"HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise SystemExit(f"Network error: {exc.reason}") from exc

    ranking_data = extract_ranking_response(response_payload)
    print_summary(ranking_data, limit=args.limit)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    search_filename = f"gb_search_{sanitize_filename(args.query)}_{timestamp}.json"
    search_path = write_json(args.save_json, ranking_data, search_filename)
    print("")
    print(f"Saved search JSON: {search_path}")

    if args.fetch_details:
        player_id, entity_id, selected_row = resolve_detail_target(
            ranking_data=ranking_data,
            detail_index=args.detail_index,
            detail_player_id=args.detail_player_id,
            detail_entity_id=args.detail_entity_id,
        )
        try:
            detail_bundle = fetch_detail_bundle(
                world=args.world,
                h_value=args.h,
                cookie_header=cookie_header,
                version=args.version,
                timeout=args.timeout,
                request_id_start=base_request_id + 1,
                player_id=player_id,
                entity_id=entity_id,
            )
        except HTTPError as exc:
            raise SystemExit(f"HTTP error {exc.code} (details): {exc.reason}") from exc
        except URLError as exc:
            raise SystemExit(f"Network error (details): {exc.reason}") from exc

        print_detail_summary(detail_bundle, selected_row=selected_row)
        detail_filename = f"gb_detail_{sanitize_filename(args.query)}_{timestamp}.json"
        detail_json_payload = {
            "player_id": detail_bundle.get("player_id"),
            "entity_id": detail_bundle.get("entity_id"),
            "responses": detail_bundle.get("responses"),
            "raw_responses": detail_bundle.get("raw_responses"),
        }
        detail_path = write_json(args.save_detail_json, detail_json_payload, detail_filename)
        print(f"Saved detail JSON: {detail_path}")


if __name__ == "__main__":
    main()
