#!/usr/bin/env python3
"""Serve the fingerprinted static build with appropriate cache headers."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


FINGERPRINTED_RESOURCE = re.compile(r"\.[0-9a-f]{12}\.(?:css|js|json)$")
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
REVALIDATE_CACHE = "no-cache"
NO_STORE_CACHE = "no-store"
USER_INPUT_PATH = "/api/user-input"
MAX_STATE_BYTES = 64 * 1024


def cache_control_for_path(request_path: str) -> str:
    path = urlsplit(request_path).path
    if path == USER_INPUT_PATH:
        return NO_STORE_CACHE
    if FINGERPRINTED_RESOURCE.search(path):
        return IMMUTABLE_CACHE
    return REVALIDATE_CACHE


def load_user_input(state_file: Path) -> dict:
    if not state_file.is_file():
        return {}
    try:
        value = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_user_input(state_file: Path, value: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=state_file.parent,
        prefix=f".{state_file.name}.",
        suffix=".tmp",
        encoding="utf-8",
        delete=False,
    ) as temporary:
        temporary.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    Path(temporary.name).replace(state_file)


class CacheAwareHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, state_file: Path, **kwargs) -> None:
        self.state_file = state_file
        super().__init__(*args, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", cache_control_for_path(self.path))
        super().end_headers()

    def send_json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == USER_INPUT_PATH:
            self.send_json(200, load_user_input(self.state_file))
            return
        super().do_GET()

    def do_PUT(self) -> None:
        if urlsplit(self.path).path != USER_INPUT_PATH:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Invalid Content-Length"})
            return
        if length < 1 or length > MAX_STATE_BYTES:
            self.send_json(413, {"error": "State payload is empty or too large"})
            return
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "State payload must be valid JSON"})
            return
        if not isinstance(value, dict):
            self.send_json(400, {"error": "State payload must be a JSON object"})
            return
        save_user_input(self.state_file, value)
        self.send_json(200, {"saved": True})

    do_POST = do_PUT


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=project_root / "dist")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "foe-gb-analysis-user-input.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    directory = args.directory.resolve()
    state_file = args.state_file.resolve()
    handler = partial(CacheAwareHandler, directory=str(directory), state_file=state_file)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Serving {directory} at http://127.0.0.1:{args.port}", flush=True)
    print(f"Saving dashboard input to {state_file}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
