#!/usr/bin/env python3
"""Log in to Forge of Empires, download treasury data, and rebuild the portal.

Credentials are read from ``.env.foe`` and are never written to generated data
or printed. The script follows the same read-only game flow captured while
exporting through Forge Hammer:

* ``ClanService.getTreasuryBag`` for the current guild stock snapshot.
* ``ClanService.getTreasuryLogs`` for contribution transactions.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import http.cookiejar
import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIAL_FILE = PROJECT_DIR / ".env.foe"
DEFAULT_DIAGNOSTIC_LOG = PROJECT_DIR / ".foe-sync-diagnostic.json"
DEFAULT_INPUT_DIR = PROJECT_DIR / "input"
DEFAULT_CONTRIBUTION_DIR = DEFAULT_INPUT_DIR / "guild-goods-contribution"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
FORGE_HX_PATH_RE = re.compile(r"(https?://[^\"']+|/[^\"']*|)cache/ForgeHX-[^\"']+\.js")
FORGE_HX_SIGNATURE_RE = re.compile(r'_signatureHash\+"([^"]+)"\+a\)')
FORGE_HX_VERSION_RE = re.compile(
    r'"version=([0-9]+\.[0-9]+)"\s*,\s*"requiredVersion=([0-9]+\.[0-9]+)"'
)
RESOURCE_BAG = {"__enum__": "ResourceBagType", "value": "ClanMain"}
CONTRIBUTION_COLUMNS = (
    "Player ID",
    "Player name",
    "Era",
    "Good",
    "Amount",
    "Message",
    "Date/Time",
)


class SyncError(RuntimeError):
    """A safe, user-facing sync failure."""


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    world: str
    market: str
    timeout: float
    contribution_lookback_days: int
    log_page_size: int
    request_delay_seconds: float
    h_value: str = ""
    client_version: str = "auto"
    signature_secret: str = ""


@dataclass(frozen=True)
class GoodInfo:
    resource_id: str
    display_name: str
    era_name: str
    era_id: int


@dataclass(frozen=True)
class LoginResult:
    world: str
    h_value: str
    index_html: str


class DiagnosticLog:
    """Permission-restricted protocol metadata with no raw secrets or game data."""

    def __init__(self, path: Path, *, mode: str = "one-shot-gateway-probe") -> None:
        expanded = path.expanduser()
        if expanded.is_symlink():
            raise SyncError("Diagnostic log path must not be a symbolic link.")
        self.path = expanded.resolve()
        self.data: dict[str, Any] = {
            "schema_version": 1,
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mode": mode,
            "status": "started",
            "phase": "configuration",
        }
        self._write()

    def update(self, **fields: Any) -> None:
        self.data.update(fields)
        self.data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        self._write()

    def append(self, field: str, value: Any) -> None:
        items = self.data.setdefault(field, [])
        if not isinstance(items, list):
            raise SyncError("Diagnostic log field has an unexpected shape.")
        items.append(value)
        self.data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2, sort_keys=True)
                handle.write("\n")
        except OSError as error:
            raise SyncError("The secure diagnostic log could not be written.") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download GoE treasury and contribution records, then refresh the portal."
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIAL_FILE,
        help="Credential file (default: .env.foe).",
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument(
        "--contribution-dir",
        type=Path,
        default=DEFAULT_CONTRIBUTION_DIR,
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download CSV files without rebuilding dashboard assets.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--login-only",
        action="store_true",
        help="Validate authentication without downloading or writing data.",
    )
    mode.add_argument(
        "--gateway-probe",
        action="store_true",
        help="Send exactly one StartupService.getData game request, log safe diagnostics, and exit.",
    )
    mode.add_argument(
        "--treasury-only",
        action="store_true",
        help="Initialize the gateway, download one treasury snapshot, and exit before contributions.",
    )
    parser.add_argument(
        "--diagnostic-log",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_LOG,
        help="One-shot gateway probe diagnostic path (default: .foe-sync-diagnostic.json).",
    )
    args = parser.parse_args()
    if (args.gateway_probe or args.treasury_only) and args.download_only:
        parser.error("--gateway-probe/--treasury-only cannot be combined with --download-only")
    return args


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = value.replace(r"\n", "\n").replace(r"\t", "\t")
            value = value.replace(r'\"', '"').replace(r"\\", "\\")
    return value


def read_env_file(path: Path, *, require_secure_permissions: bool = True) -> dict[str, str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise SyncError(
            f"Credential file not found: {path}. Copy .env.foe.example to .env.foe first."
        )

    if require_secure_permissions and os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise SyncError(
                f"Credential file permissions are too open ({mode:03o}); run chmod 600 {path.name}."
            )

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SyncError(f"Invalid credential line {line_number}: expected NAME=value.")
        name, value = line.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise SyncError(f"Invalid setting name on credential line {line_number}.")
        values[name] = _unquote_env_value(value)
    return values


def _setting(values: dict[str, str], name: str, default: str = "") -> str:
    return os.environ.get(name, values.get(name, default)).strip()


def load_config(path: Path) -> Config:
    values = read_env_file(path)
    username = _setting(values, "FOE_USERNAME")
    password = _setting(values, "FOE_PASSWORD")
    world = _setting(values, "FOE_WORLD", "us24").lower()
    if not username or not password:
        raise SyncError("FOE_USERNAME and FOE_PASSWORD must be filled in within .env.foe.")
    if not re.fullmatch(r"[a-z]{2,4}[0-9]+", world):
        raise SyncError("FOE_WORLD must look like us24, en1, or de12.")

    market_match = re.match(r"[a-z]+", world)
    market = _setting(values, "FOE_MARKET", market_match.group(0) if market_match else "us")
    try:
        timeout = float(_setting(values, "FOE_TIMEOUT_SECONDS", "30"))
        lookback = int(_setting(values, "FOE_CONTRIBUTION_LOOKBACK_DAYS", "3"))
        page_size = int(_setting(values, "FOE_LOG_PAGE_SIZE", "100"))
        delay = float(_setting(values, "FOE_REQUEST_DELAY_SECONDS", "0.10"))
    except ValueError as error:
        raise SyncError(f"Invalid numeric setting in {path.name}: {error}") from error
    if timeout <= 0:
        raise SyncError("FOE_TIMEOUT_SECONDS must be greater than zero.")
    if lookback < 1:
        raise SyncError("FOE_CONTRIBUTION_LOOKBACK_DAYS must be at least 1.")
    if not 1 <= page_size <= 1000:
        raise SyncError("FOE_LOG_PAGE_SIZE must be between 1 and 1000.")
    if delay < 0:
        raise SyncError("FOE_REQUEST_DELAY_SECONDS cannot be negative.")

    return Config(
        username=username,
        password=password,
        world=world,
        market=market,
        timeout=timeout,
        contribution_lookback_days=lookback,
        log_page_size=page_size,
        request_delay_seconds=delay,
        h_value=_setting(values, "FOE_H"),
        client_version=_setting(values, "FOE_CLIENT_VERSION", "auto"),
        signature_secret=_setting(values, "FOE_SIGNATURE_SECRET"),
    )


def _decode_response(response: Any) -> str:
    raw = response.read()
    content_encoding = str(response.headers.get("Content-Encoding", "")).lower().strip()
    if content_encoding in {"gzip", "x-gzip"} or raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def _json_object(text: str, context: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise SyncError(f"{context} returned an invalid JSON response.") from error
    if not isinstance(payload, dict):
        raise SyncError(f"{context} returned an unexpected response shape.")
    return payload


def extract_gateway_h(urls_and_html: Iterable[str]) -> str:
    patterns = (
        re.compile(r"/game/json\?h=([A-Za-z0-9_-]{10,})"),
        re.compile(r'(?:gatewayH|gateway_hash)\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})'),
        re.compile(r'["\'](?:gatewayH|gateway_hash|h)["\']\s*:\s*["\']([A-Za-z0-9_-]{10,})'),
    )
    for value in urls_and_html:
        if not value:
            continue
        parsed = urlparse(value)
        host_prefix = (parsed.hostname or "").split(".")[0]
        is_game_url = bool(
            parsed.scheme
            and re.fullmatch(r"[a-z]{2,4}[0-9]+", host_prefix)
            and parsed.path.startswith("/game/")
        )
        query_h = parse_qs(parsed.query).get("h", []) if is_game_url else []
        if query_h and re.fullmatch(r"[A-Za-z0-9_-]{10,}", query_h[0]):
            return query_h[0]
        for pattern in patterns:
            match = pattern.search(value)
            if match:
                return match.group(1)
    return ""


def extract_csrf(html: str) -> str:
    patterns = (
        re.compile(r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)', re.IGNORECASE),
        re.compile(r'csrfToken\s*[:=]\s*["\']([^"\']+)', re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(html)
        if match:
            return match.group(1)
    return ""


def extract_forge_hx_config(bundle_js: str) -> tuple[str, str]:
    secret_match = FORGE_HX_SIGNATURE_RE.search(bundle_js)
    version_match = FORGE_HX_VERSION_RE.search(bundle_js)
    if not secret_match or not version_match:
        raise SyncError(
            "The current ForgeHX client configuration could not be parsed; "
            "no game API request was sent."
        )
    version = version_match.group(1)
    required_version = version_match.group(2)
    if version != required_version:
        raise SyncError(
            "ForgeHX reports different client and required versions; "
            "no game API request was sent."
        )
    return version, secret_match.group(1)


def find_forge_hx_bundle_candidates(
    index_html: str, index_url: str, market: str
) -> tuple[list[str], str]:
    candidates: list[str] = []
    for match in FORGE_HX_PATH_RE.finditer(index_html):
        candidate = match.group(0)
        absolute = candidate if candidate.startswith("http") else urljoin(index_url, candidate)
        parsed = urlparse(absolute)
        safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if safe_url not in candidates:
            candidates.append(safe_url)

    expected_host = f"foe{market}.innogamescdn.com"
    matching = [url for url in candidates if urlparse(url).hostname == expected_host]
    if len(matching) != 1:
        raise SyncError(
            f"Expected exactly one ForgeHX bundle on {expected_host}; "
            "no game API request was sent."
        )
    return candidates, matching[0]


class FoeClient:
    def __init__(self, config: Config, diagnostic: DiagnosticLog | None = None) -> None:
        self.config = config
        self.diagnostic = diagnostic
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.world = config.world
        self.h_value = config.h_value
        self.client_version = config.client_version
        self.signature_secret = config.signature_secret
        # This urllib session does not execute the game client, so it has not
        # consumed any /game/json request IDs. The first gateway request is 1;
        # every subsequent outbound call must use the next integer.
        self._request_id = 0
        self._authentication_attempted = False
        self._gateway_initialization_attempted = False
        self._gateway_initialized = False
        self._last_gateway_http_status: int | None = None
        self.index_html = ""
        self.game_goods: list[dict[str, Any]] = []

    def _record(self, **fields: Any) -> None:
        if self.diagnostic:
            self.diagnostic.update(**fields)

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        request_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Encoding": "identity",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            request_headers.update(headers)
        request = Request(url=url, data=data, headers=request_headers, method=method)
        is_gateway = urlparse(url).path == "/game/json"
        try:
            with self.opener.open(request, timeout=self.config.timeout) as response:
                text = _decode_response(response)
                if is_gateway:
                    self._last_gateway_http_status = getattr(response, "status", None)
                    self._record(
                        phase="gateway_response",
                        gateway_http_status=getattr(response, "status", None),
                        gateway_response_bytes=len(text.encode("utf-8")),
                        gateway_response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
                return response.geturl(), text
        except HTTPError as error:
            if is_gateway:
                self._record(
                    status="failed",
                    phase="gateway_http_error",
                    gateway_http_status=error.code,
                    failure_type="HTTPError",
                )
            raise
        except URLError:
            if is_gateway:
                self._record(
                    status="failed",
                    phase="gateway_network_error",
                    failure_type="URLError",
                )
            raise

    def _post_json(self, url: str, payload: dict[str, Any], referer: str) -> dict[str, Any]:
        _, text = self._request(
            url,
            method="POST",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": f"{urlparse(url).scheme}://{urlparse(url).netloc}",
                "Referer": referer,
            },
        )
        return _json_object(text, "Forge of Empires login")

    def _select_world(self) -> tuple[str, str]:
        portal_url = f"https://{self.config.market}0.forgeofempires.com/page/"
        _, portal_html = self._request(portal_url)
        csrf = extract_csrf(portal_html)
        select_url = f"https://{self.config.market}0.forgeofempires.com/start/index?action=play_now_login"
        if csrf:
            select_url += "&" + urlencode({"h": csrf})
        form = urlencode({"json": json.dumps({"world_id": self.config.world})}).encode("utf-8")
        _, text = self._request(
            select_url,
            method="POST",
            data=form,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": f"https://{self.config.market}0.forgeofempires.com",
                "Referer": portal_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        response = _json_object(text, "Forge of Empires world selection")
        login_url = str(response.get("login_url") or response.get("redirect") or "").strip()
        if not login_url:
            raise SyncError(
                f"Login succeeded, but world {self.config.world} could not be selected automatically."
            )
        return self._request(urljoin(portal_url, login_url))

    def authenticate(self) -> LoginResult:
        if self._authentication_attempted:
            raise SyncError("Authentication was already attempted; refusing to repeat it.")
        self._authentication_attempted = True
        self._record(phase="authentication", authentication_attempted=True)
        login_base = f"https://{self.config.market}-play.forgeofempires.com"
        landing_url = login_base + "/?ref=treasury-sync"
        self._request(landing_url)
        login = self._post_json(
            login_base + "/api/login",
            {
                "username": self.config.username,
                "password": self.config.password,
                "useRememberMe": False,
            },
            landing_url,
        )
        errors = login.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            code = str(first.get("code") or "login rejected")
            raise SyncError(f"Forge of Empires login failed: {code}.")
        redirect_url = str(login.get("redirectUrl") or "").strip()
        if not redirect_url:
            raise SyncError("Forge of Empires login did not return a game redirect.")

        final_url, final_html = self._request(urljoin(login_base, redirect_url))
        host = (urlparse(final_url).hostname or "").split(".")[0]
        if host != self.config.world or "/game/index" not in urlparse(final_url).path:
            final_url, final_html = self._select_world()

        host = (urlparse(final_url).hostname or "").split(".")[0]
        if host != self.config.world:
            raise SyncError(
                f"Login opened {host or 'an unknown world'} instead of configured world "
                f"{self.config.world}."
            )

        index_url = f"https://{self.config.world}.forgeofempires.com/game/index?"
        index_final_url, index_html = self._request(index_url)
        self.index_html = index_html
        self.h_value = self.h_value or extract_gateway_h(
            (index_final_url, index_html, final_url, final_html, redirect_url)
        )
        if not self.h_value:
            raise SyncError(
                "Login succeeded, but the game gateway token was not present in the login response. "
                "Set FOE_H temporarily from a game/json?h=... request and report this response change."
            )
        self._record(
            phase="login_complete",
            authentication_result="success",
            world=self.config.world,
            session_cookie_count=len(list(self.cookies)),
            gateway_token_fingerprint=hashlib.sha256(self.h_value.encode("utf-8")).hexdigest()[:16],
        )
        self._discover_client_config(index_html, index_url)
        return LoginResult(self.config.world, self.h_value, index_html)

    def _discover_client_config(self, index_html: str, index_url: str) -> None:
        configured_version = self.client_version.strip()
        if configured_version.lower() == "auto":
            configured_version = ""
        configured_secret = self.signature_secret.strip()

        try:
            bundle_candidates, bundle_url = find_forge_hx_bundle_candidates(
                index_html, index_url, self.config.market
            )
        except SyncError:
            raw_candidates = [
                match.group(0) for match in FORGE_HX_PATH_RE.finditer(index_html)
            ]
            safe_candidates = []
            for candidate in raw_candidates:
                parsed = urlparse(
                    candidate if candidate.startswith("http") else urljoin(index_url, candidate)
                )
                safe_candidates.append(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
            self._record(
                status="failed",
                phase="client_bundle_candidate_error",
                forge_hx_bundle_candidates=list(dict.fromkeys(safe_candidates)),
                expected_bundle_host=f"foe{self.config.market}.innogamescdn.com",
                failure_type="BundleCandidateError",
            )
            raise
        if not bundle_candidates:
            raise SyncError(
                "The current ForgeHX bundle path was not found; no game API request was sent."
            )
        parsed_bundle_url = urlparse(bundle_url)
        safe_bundle_url = (
            f"{parsed_bundle_url.scheme}://{parsed_bundle_url.netloc}{parsed_bundle_url.path}"
        )
        self._record(
            phase="client_bundle_request",
            forge_hx_bundle_candidates=bundle_candidates,
            forge_hx_bundle=safe_bundle_url,
        )
        try:
            _, bundle_js = self._request(
                bundle_url,
                headers={
                    "Origin": f"https://{self.config.world}.forgeofempires.com",
                    "Referer": index_url,
                },
            )
        except HTTPError as error:
            self._record(
                status="failed",
                phase="client_bundle_http_error",
                failure_type="HTTPError",
                client_bundle_http_status=error.code,
            )
            raise SyncError(
                "The current ForgeHX bundle could not be loaded; no game API request was sent."
            ) from error
        except URLError as error:
            reason = error.reason
            self._record(
                status="failed",
                phase="client_bundle_network_error",
                failure_type="URLError",
                failure_reason_type=type(reason).__name__,
                failure_reason=str(reason)[:256],
            )
            raise SyncError(
                "The current ForgeHX bundle could not be loaded; no game API request was sent."
            ) from error
        except OSError as error:
            self._record(
                status="failed",
                phase="client_bundle_io_error",
                failure_type=type(error).__name__,
                failure_errno=error.errno,
                failure_reason=str(error)[:256],
            )
            raise SyncError(
                "The current ForgeHX bundle could not be loaded; no game API request was sent."
            ) from error

        discovered_version, discovered_secret = extract_forge_hx_config(bundle_js)
        if configured_version and configured_version != discovered_version:
            raise SyncError(
                "FOE_CLIENT_VERSION does not match the current ForgeHX bundle; "
                "no game API request was sent."
            )
        if configured_secret and configured_secret != discovered_secret:
            raise SyncError(
                "FOE_SIGNATURE_SECRET does not match the current ForgeHX bundle; "
                "no game API request was sent."
            )
        self.client_version = discovered_version
        self.signature_secret = discovered_secret
        self._record(
            phase="client_configuration",
            forge_hx_bundle=safe_bundle_url,
            forge_hx_sha256=hashlib.sha256(bundle_js.encode("utf-8")).hexdigest(),
            client_version=discovered_version,
            signature_secret_fingerprint=(
                hashlib.sha256(discovered_secret.encode("utf-8")).hexdigest()[:16]
            ),
        )

    def initialize_gateway(self) -> None:
        if self._gateway_initialized:
            return
        if self._gateway_initialization_attempted:
            raise SyncError("Gateway initialization was already attempted; refusing to repeat it.")
        self._gateway_initialization_attempted = True

        # A fresh authenticated HTTP session has not executed the JavaScript
        # client startup sequence. StartupService must initialize game state
        # before the read-only clan services are called. The manual Chrome
        # capture showed StartupService.getData before getOwnClanData and the
        # treasury calls; unrelated telemetry and UI preload calls are omitted.
        startup_data = self.call("StartupService", "getData", [])
        self.game_goods = extract_startup_goods(startup_data)
        self.call("ClanService", "getOwnClanData", [])
        self._gateway_initialized = True

    @staticmethod
    def _server_request(
        request_class: str,
        request_method: str,
        request_data: Sequence[Any],
        request_id: int,
    ) -> dict[str, Any]:
        return {
            "__class__": "ServerRequest",
            "requestData": list(request_data),
            "requestClass": request_class,
            "requestMethod": request_method,
            "requestId": request_id,
        }

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def call(self, request_class: str, request_method: str, request_data: Sequence[Any]) -> Any:
        request_id = self._next_request_id()
        body = json.dumps(
            [self._server_request(request_class, request_method, request_data, request_id)],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        signature = hashlib.md5(
            (self.h_value + self.signature_secret + body).encode("utf-8")
        ).hexdigest()[1:11]
        self._record(
            phase="gateway_request",
            gateway_request={
                "request_id": request_id,
                "request_class": request_class,
                "request_method": request_method,
                "request_data_items": len(request_data),
                "body_bytes": len(body.encode("utf-8")),
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "signature_fingerprint": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
                "signature_digest": "md5",
                "signature_slice": "1:11",
                "path": "/game/json",
            },
        )
        if self.diagnostic:
            self.diagnostic.append(
                "gateway_requests",
                {
                    "request_id": request_id,
                    "request_class": request_class,
                    "request_method": request_method,
                    "request_data_items": len(request_data),
                    "body_bytes": len(body.encode("utf-8")),
                    "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    "signature_fingerprint": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
                },
            )
        gateway_url = (
            f"https://{self.config.world}.forgeofempires.com/game/json?"
            + urlencode({"h": self.h_value})
        )
        _, text = self._request(
            gateway_url,
            method="POST",
            data=body.encode("utf-8"),
            headers={
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Client-Identification": (
                    f"version={self.client_version}; requiredVersion={self.client_version}; "
                    "platform=bro; platformType=html5; platformVersion=web"
                ),
                "Signature": signature,
                "Origin": f"https://{self.config.world}.forgeofempires.com",
                "Referer": f"https://{self.config.world}.forgeofempires.com/game/index?",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            self._record(
                status="failed",
                phase="gateway_response_parse",
                response_json_valid=False,
                failure_type="JSONDecodeError",
            )
            raise SyncError(f"{request_class}.{request_method} returned invalid JSON.") from error
        if not isinstance(payload, list):
            self._record(
                status="failed",
                phase="gateway_response_parse",
                response_json_valid=True,
                response_shape=type(payload).__name__,
            )
            raise SyncError(f"{request_class}.{request_method} returned an unexpected response.")
        response_summary = [
            {
                "request_id": item.get("requestId"),
                "response_class": item.get("__class__"),
                "request_class": item.get("requestClass"),
                "request_method": item.get("requestMethod"),
                "error_code": item.get("errorCode"),
                "title": item.get("title"),
            }
            for item in payload
            if isinstance(item, dict)
        ]
        self._record(
            phase="gateway_response_parse",
            response_json_valid=True,
            response_shape="list",
            response_item_count=len(payload),
            response_items=response_summary,
        )
        for item in payload:
            if (
                not isinstance(item, dict)
                or item.get("requestId") != request_id
                or item.get("requestClass") != request_class
                or item.get("requestMethod") != request_method
            ):
                continue
            if item.get("errorCode") or item.get("errorMessage"):
                code = item.get("errorCode") or "server error"
                self._record(
                    status="failed",
                    phase="gateway_response_match",
                    matched_request_id=request_id,
                    gateway_error_code=code,
                )
                raise SyncError(f"{request_class}.{request_method} failed: {code}.")
            self._record(
                status="success",
                phase="complete",
                matched_request_id=request_id,
                response_data_type=type(item.get("responseData")).__name__,
            )
            if self.diagnostic:
                self.diagnostic.append(
                    "gateway_results",
                    {
                        "request_id": request_id,
                        "http_status": self._last_gateway_http_status,
                        "response_json_valid": True,
                        "response_item_count": len(payload),
                        "matched": True,
                        "response_data_type": type(item.get("responseData")).__name__,
                    },
                )
            return item.get("responseData")
        generic_error = next(
            (
                item
                for item in payload
                if isinstance(item, dict)
                and (item.get("errorCode") or item.get("errorMessage") or item.get("title"))
            ),
            None,
        )
        if generic_error:
            code = generic_error.get("errorCode") or generic_error.get("title") or "server error"
            self._record(
                status="failed",
                phase="gateway_response_match",
                matched_request_id=None,
                gateway_error_code=code,
            )
            raise SyncError(f"{request_class}.{request_method} failed: {code}.")
        self._record(
            status="failed",
            phase="gateway_response_match",
            matched_request_id=None,
            failure_type="MissingResponse",
        )
        raise SyncError(f"{request_class}.{request_method} response was missing.")


def normalize_good(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def extract_startup_goods(startup_data: Any) -> list[dict[str, Any]]:
    """Return the ID/name catalog Forge Hammer reads from StartupService."""
    if not isinstance(startup_data, dict) or not isinstance(startup_data.get("goodsList"), list):
        raise SyncError("StartupService.getData did not contain the game goods list.")

    goods: list[dict[str, Any]] = []
    for item in startup_data["goodsList"]:
        if not isinstance(item, dict):
            raise SyncError("The game goods list contained an invalid entry.")
        resource_id = item.get("id")
        display_name = item.get("name")
        if not isinstance(resource_id, str) or not resource_id:
            raise SyncError("The game goods list contained an entry without an ID.")
        if not isinstance(display_name, str) or not display_name:
            raise SyncError("The game goods list contained an entry without a name.")
        goods.append(item)
    return goods


class GoodsCatalog:
    def __init__(
        self,
        goods: Sequence[str],
        game_goods: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        if len(goods) % 5:
            raise SyncError("Treasury history does not contain complete five-good era groups.")
        self.goods = list(goods)
        self.by_normalized: dict[str, GoodInfo] = {}
        self.by_display_name: dict[str, GoodInfo] = {}
        age_names = _age_names_for_goods(len(goods))
        age_start = len(_all_age_names()) - len(age_names)
        game_goods_by_name: dict[str, dict[str, Any]] = {}
        if game_goods is not None:
            for item in game_goods:
                resource_id = item.get("id") if isinstance(item, dict) else None
                display_name = item.get("name") if isinstance(item, dict) else None
                if not isinstance(resource_id, str) or not isinstance(display_name, str):
                    raise SyncError("The game goods list contained an invalid entry.")
                normalized_name = normalize_good(display_name)
                if normalized_name in game_goods_by_name:
                    raise SyncError(f"The game goods list contains duplicate name {display_name!r}.")
                game_goods_by_name[normalized_name] = item

        for index, display_name in enumerate(goods):
            age_offset = index // 5
            era_name = age_names[age_offset]
            era_id = age_start + age_offset + 2
            normalized_name = normalize_good(display_name)
            resource_id = display_name
            if game_goods is not None:
                game_good = game_goods_by_name.get(normalized_name)
                if game_good is None:
                    raise SyncError(
                        f"The current game goods list does not contain {display_name!r}."
                    )
                resource_id = str(game_good["id"])
            info = GoodInfo(
                resource_id=resource_id,
                display_name=display_name,
                era_name=era_name,
                era_id=era_id,
            )
            self.by_display_name[display_name] = info
            for alias in (display_name, resource_id):
                normalized_alias = normalize_good(alias)
                existing = self.by_normalized.get(normalized_alias)
                if existing is not None and existing != info:
                    raise SyncError(f"The game goods mapping is ambiguous for {alias!r}.")
                self.by_normalized[normalized_alias] = info

    def resolve(self, resource_id: str) -> GoodInfo:
        info = self.by_normalized.get(normalize_good(resource_id))
        if info is None:
            raise SyncError(
                f"Game returned unknown treasury resource {resource_id!r}; refresh the goods mapping."
            )
        return info

    def resource_id_for(self, display_name: str) -> str:
        try:
            return self.by_display_name[display_name].resource_id
        except KeyError as error:
            raise SyncError(f"Treasury history contains unknown good {display_name!r}.") from error


def _age_names_for_goods(good_count: int) -> list[str]:
    age_order = _all_age_names()
    age_count = good_count // 5
    if age_count > len(age_order):
        raise SyncError("Treasury history contains more eras than the dashboard supports.")
    return age_order[len(age_order) - age_count :]


def _all_age_names() -> list[str]:
    from generate_treasury_dashboard import AGE_ORDER

    return AGE_ORDER


def find_latest_treasury_history(input_dir: Path) -> tuple[Path, list[str], list[Any]]:
    from generate_treasury_dashboard import read_export

    candidates: list[tuple[dt.date, int, Path, list[str], list[Any]]] = []
    for path in input_dir.glob("*.csv"):
        if not path.is_file():
            continue
        try:
            goods, rows = read_export(path)
        except (OSError, ValueError):
            continue
        if not goods or len(goods) % 5:
            continue
        candidates.append((rows[-1][0], len(rows), path, goods, rows))
    if not candidates:
        raise SyncError(f"No valid treasury history CSV found in {input_dir}.")
    _, _, path, goods, rows = max(candidates, key=lambda item: (item[0], item[1], item[2].name))
    return path, goods, rows


def _treasury_resources(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise SyncError("Treasury response is not an object.")
    resources = response.get("resources")
    if isinstance(resources, dict) and isinstance(resources.get("resources"), dict):
        resources = resources["resources"]
    if not isinstance(resources, dict):
        raise SyncError("Treasury response did not contain a resource map.")
    return resources


def write_treasury_snapshot(
    *,
    output_dir: Path,
    goods: Sequence[str],
    rows: Sequence[tuple[dt.date, dict[str, int]]],
    resources: dict[str, Any],
    snapshot_date: dt.date,
    game_goods: Sequence[dict[str, Any]] | None = None,
) -> tuple[Path, int]:
    catalog = GoodsCatalog(goods, game_goods=game_goods)
    snapshot: dict[str, int] = {}
    for good in goods:
        resource_id = catalog.resource_id_for(good)
        value = resources.get(resource_id, 0)
        try:
            snapshot[good] = int(value)
        except (TypeError, ValueError) as error:
            raise SyncError(f"Treasury amount for {good} is not numeric.") from error

    merged = {date: dict(values) for date, values in rows}
    merged[snapshot_date] = snapshot
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"stats-{snapshot_date.isoformat()}.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        # Forge Hammer quotes the text header/date fields and leaves numeric
        # treasury values unquoted.
        writer = csv.writer(
            handle,
            delimiter=";",
            quoting=csv.QUOTE_NONNUMERIC,
            lineterminator="\n",
        )
        writer.writerow(["DateTime", *goods])
        for date in sorted(merged):
            writer.writerow(
                [f"{date.isoformat()} 00:00:00", *[merged[date].get(good, 0) for good in goods]]
            )
    return output_path, len(merged)


def parse_game_timestamp(value: str) -> dt.datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for pattern in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return dt.datetime.strptime(raw, pattern)
        except ValueError:
            pass
    raise SyncError(f"Unsupported contribution timestamp returned by the game: {value!r}")


def latest_contribution_timestamp(input_dir: Path) -> dt.datetime | None:
    from generate_contribution_dashboard import read_export

    latest: dt.datetime | None = None
    for path in input_dir.glob("*.csv"):
        if not path.is_file():
            continue
        try:
            rows = read_export(path)
        except (OSError, ValueError):
            continue
        if rows:
            timestamp = rows[0]["timestamp"]
            if isinstance(timestamp, dt.datetime) and (latest is None or timestamp > latest):
                latest = timestamp
    return latest


def fetch_contribution_logs(
    client: FoeClient,
    *,
    cutoff: dt.datetime,
    page_size: int,
    delay_seconds: float,
) -> tuple[list[dict[str, Any]], int, int]:
    logs: list[dict[str, Any]] = []
    offset = 0
    total_count = 0
    page_count = 0
    while True:
        response = client.call(
            "ClanService",
            "getTreasuryLogs",
            [page_size, offset, RESOURCE_BAG],
        )
        if not isinstance(response, dict) or not isinstance(response.get("logs"), list):
            raise SyncError("Contribution response did not contain a log page.")
        page = [item for item in response["logs"] if isinstance(item, dict)]
        total_count = int(response.get("count") or total_count or len(page))
        page_count += 1
        if not page:
            break
        logs.extend(page)
        timestamps = [parse_game_timestamp(str(item.get("createdAt") or "")) for item in page]
        offset += len(page)
        if min(timestamps) <= cutoff or offset >= total_count:
            break
        if page_count >= 5000:
            raise SyncError("Contribution pagination exceeded the 5,000-page safety limit.")
        if delay_seconds:
            time.sleep(delay_seconds)
    return logs, total_count, page_count


def _contribution_key(row: dict[str, Any]) -> tuple[Any, ...]:
    player = str(row["player_id"]) or str(row["player_name"])
    return (
        player,
        row["era"],
        row["good"],
        row["amount"],
        row["message"],
        row["timestamp"],
    )


def transform_contribution_logs(
    logs: Sequence[dict[str, Any]],
    *,
    catalog: GoodsCatalog,
    cutoff: dt.datetime,
) -> list[dict[str, Any]]:
    rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in logs:
        timestamp = parse_game_timestamp(str(item.get("createdAt") or ""))
        if timestamp < cutoff:
            continue
        resource_id = str(item.get("resource") or "").strip()
        info = catalog.resolve(resource_id)
        player = item.get("player")
        if not isinstance(player, dict):
            raise SyncError("Contribution log entry is missing player information.")
        row = {
            "player_id": str(player.get("player_id") or "").strip(),
            "player_name": str(player.get("name") or "Unknown player").strip(),
            "era": f"{info.era_id:02d} - {info.era_name}",
            "good": info.display_name,
            "amount": int(item.get("amount") or 0),
            "message": str(item.get("action") or "Unspecified").strip(),
            "timestamp": timestamp,
        }
        rows_by_key[_contribution_key(row)] = row
    return sorted(rows_by_key.values(), key=lambda row: row["timestamp"], reverse=True)


def write_contribution_export(
    rows: Sequence[dict[str, Any]], output_dir: Path, snapshot_date: dt.date
) -> Path:
    if not rows:
        raise SyncError("No contribution records were returned within the configured overlap window.")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"GuildTreasury-{snapshot_date.isoformat()}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerow(CONTRIBUTION_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row["player_id"],
                    row["player_name"],
                    row["era"],
                    row["good"],
                    row["amount"],
                    row["message"],
                    row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )
    return output_path


def rebuild_dashboard(treasury_csv: Path) -> None:
    subprocess.run(
        [sys.executable, "-B", "generate_treasury_dashboard.py", "--csv", str(treasury_csv)],
        cwd=PROJECT_DIR,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-B", "generate_contribution_dashboard.py"],
        cwd=PROJECT_DIR,
        check=True,
    )


def main() -> int:
    args = parse_args()
    diagnostic: DiagnosticLog | None = None
    try:
        config = load_config(args.credentials)
        if args.gateway_probe or args.treasury_only:
            diagnostic = DiagnosticLog(
                args.diagnostic_log,
                mode=("one-shot-gateway-probe" if args.gateway_probe else "treasury-only"),
            )
            diagnostic.update(world=config.world)
        client = FoeClient(config, diagnostic=diagnostic)
        login = client.authenticate()
        print(
            f"Authenticated to {login.world}; client version {client.client_version}. "
            "Credentials remain local."
        )
        if args.login_only:
            return 0
        if args.gateway_probe:
            client.call("StartupService", "getData", [])
            print(
                f"One-shot gateway probe succeeded with request ID 1. "
                f"Diagnostic: {args.diagnostic_log.resolve()}"
            )
            return 0

        client.initialize_gateway()
        _source_path, goods, treasury_rows = find_latest_treasury_history(args.input_dir)
        catalog = GoodsCatalog(goods, game_goods=client.game_goods)
        treasury_response = client.call("ClanService", "getTreasuryBag", [RESOURCE_BAG])
        resources = _treasury_resources(treasury_response)
        if diagnostic:
            diagnostic.update(
                phase="treasury_validation",
                treasury_resource_count=len(resources),
                treasury_resource_keys=sorted(str(key) for key in resources),
            )
        snapshot_date = dt.datetime.now().astimezone().date()
        treasury_path, snapshot_count = write_treasury_snapshot(
            output_dir=args.input_dir,
            goods=goods,
            rows=treasury_rows,
            resources=resources,
            snapshot_date=snapshot_date,
            game_goods=client.game_goods,
        )
        if args.treasury_only:
            if diagnostic:
                diagnostic.update(
                    status="success",
                    phase="treasury_written",
                    treasury_good_count=len(goods),
                    treasury_snapshot_count=snapshot_count,
                    treasury_output=treasury_path.relative_to(PROJECT_DIR).as_posix(),
                )
            print(
                f"Treasury: {treasury_path.relative_to(PROJECT_DIR)} "
                f"({snapshot_count} daily snapshots, {len(goods)} goods)."
            )
            print("Treasury-only sync complete; no contribution requests were sent.")
            return 0

        latest = latest_contribution_timestamp(args.contribution_dir)
        anchor = latest or dt.datetime.combine(snapshot_date, dt.time())
        cutoff = anchor - dt.timedelta(days=config.contribution_lookback_days)
        raw_logs, server_count, page_count = fetch_contribution_logs(
            client,
            cutoff=cutoff,
            page_size=config.log_page_size,
            delay_seconds=config.request_delay_seconds,
        )
        contribution_rows = transform_contribution_logs(raw_logs, catalog=catalog, cutoff=cutoff)
        contribution_path = write_contribution_export(
            contribution_rows,
            args.contribution_dir,
            snapshot_date,
        )

        print(
            f"Treasury: {treasury_path.relative_to(PROJECT_DIR)} "
            f"({snapshot_count} daily snapshots, {len(goods)} goods)."
        )
        print(
            f"Contributions: {contribution_path.relative_to(PROJECT_DIR)} "
            f"({len(contribution_rows)} overlap records from {page_count} pages; "
            f"server reports {server_count} total)."
        )
        if not args.download_only:
            rebuild_dashboard(treasury_path)
            print("Dashboard treasury and contribution data refreshed.")
        return 0
    except SyncError as error:
        if diagnostic:
            fields: dict[str, Any] = {
                "status": "failed",
                "failure_message": str(error),
            }
            if "failure_type" not in diagnostic.data:
                fields["failure_type"] = type(error).__name__
            diagnostic.update(**fields)
        print(f"Sync failed: {error}", file=sys.stderr)
        return 1
    except HTTPError as error:
        if diagnostic:
            diagnostic.update(
                status="failed",
                failure_type="HTTPError",
                gateway_http_status=error.code,
            )
        print(f"Sync failed: HTTP {error.code} from Forge of Empires.", file=sys.stderr)
        return 1
    except URLError as error:
        if diagnostic:
            diagnostic.update(status="failed", failure_type="URLError")
        print(f"Sync failed: network error: {error.reason}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"Sync failed: dashboard generator exited with {error.returncode}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
