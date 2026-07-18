#!/usr/bin/env python3
"""CLI and end-to-end API smoke checks for Random Draw V2.

The CLI only talks to the documented HTTP API. It does not import application
internals, so the same path works against a local process or a disposable test
environment. Do not run the ``smoke`` command against production: it creates and
ends a room.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    """An HTTP or transport error with a safe, printable message."""


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        host_token: str | None = None,
        accept: str = "application/json",
    ) -> tuple[Any, str]:
        data = None
        headers = {"Accept": accept, "User-Agent": "random-draw-v2-smoke/1"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if host_token:
            headers["X-Host-Token"] = host_token

        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                content_type = response.headers.get_content_type()
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("detail", body)
            except json.JSONDecodeError:
                detail = body
            raise ApiError(f"{method} {path}: HTTP {error.code}: {detail}") from None
        except URLError as error:
            raise ApiError(f"{method} {path}: {error.reason}") from None

        if content_type == "application/json":
            return json.loads(body), content_type
        return body, content_type


def lookup_path(room: str) -> str:
    return f"/api/rooms/{quote(room.strip(), safe='')}"


def token_from(args: argparse.Namespace) -> str | None:
    return getattr(args, "host_token", None) or os.environ.get(
        "RANDOM_DRAW_HOST_TOKEN"
    )


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"invalid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run_command(args: argparse.Namespace, client: ApiClient) -> None:
    if args.command == "create":
        payload = {
            "mode": args.mode,
            "config": args.config,
            "draw_policy": args.draw_policy,
            "host_name": args.host_name,
        }
        result, _ = client.request("POST", "/api/rooms", payload=payload)
        print_json(result)
        return

    path = lookup_path(args.room)
    if args.command == "state":
        result, _ = client.request("GET", path)
    elif args.command == "draw":
        result, _ = client.request(
            "POST",
            f"{path}/draw",
            payload={"actor": args.actor, "count": args.count},
            host_token=token_from(args),
        )
    elif args.command == "configure":
        payload: dict[str, Any] = {"config": args.config}
        if args.draw_policy:
            payload["draw_policy"] = args.draw_policy
        result, _ = client.request(
            "PATCH", path, payload=payload, host_token=token_from(args)
        )
    elif args.command in {"reset", "invalidate", "end"}:
        result, _ = client.request(
            "POST",
            f"{path}/{args.command}",
            payload={"actor": args.actor},
            host_token=token_from(args),
        )
    elif args.command == "export":
        query = urlencode({"format": args.format})
        result, content_type = client.request("GET", f"{path}/export?{query}")
        if isinstance(result, bytes):
            if args.output:
                args.output.write_bytes(result)
                print(f"wrote {args.output} ({content_type})")
            else:
                sys.stdout.buffer.write(result)
        else:
            print_json(result)
    elif args.command == "qr":
        result, content_type = client.request("GET", f"{path}/qr.svg")
        if not isinstance(result, bytes) or content_type not in {
            "image/svg+xml",
            "application/xml",
            "text/xml",
        }:
            raise ApiError("QR endpoint did not return SVG/XML")
        args.output.write_bytes(result)
        print(f"wrote {args.output} ({content_type})")
    else:  # pragma: no cover - argparse constrains command names
        raise ApiError(f"unsupported command: {args.command}")

    if args.command not in {"export", "qr"}:
        print_json(result)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ApiError(f"smoke assertion failed: {message}")


def run_smoke(args: argparse.Namespace, client: ApiClient) -> None:
    """Exercise creation, lookup, canonical draw state, audit, and host actions."""

    health, _ = client.request("GET", "/health")
    require(health.get("status") == "healthy", "health endpoint")

    created, _ = client.request(
        "POST",
        "/api/rooms",
        payload={
            "mode": "numbers",
            "config": {
                "min": 1,
                "max": 3,
                "with_replacement": False,
                "draw_count": 1,
            },
            "draw_policy": "host_only",
            "host_name": "CLI host",
        },
    )
    room = created["room"]
    token = created["host_token"]
    code = room["code"]
    require(len(code) <= 10, "short room code")

    looked_up, _ = client.request("GET", f"/api/rooms/lookup/{quote(code)}")
    require(looked_up["room"]["id"] == room["id"], "short-code lookup")

    seen: set[str] = set()
    for _ in range(3):
        drawn, _ = client.request(
            "POST",
            f"{lookup_path(code)}/draw",
            payload={"actor": "CLI host", "count": 1},
            host_token=token,
        )
        latest = drawn["room"]["latest_result"]
        values = latest if isinstance(latest, list) else [latest]
        seen.update(str(value) for value in values)
    require(len(seen) == 3, "no-replacement draw exhausted three unique values")
    require(drawn["room"]["remaining_count"] == 0, "remaining count reached zero")

    invalidated, _ = client.request(
        "POST",
        f"{lookup_path(code)}/invalidate",
        payload={"actor": "CLI host"},
        host_token=token,
    )
    require(invalidated["room"]["remaining_count"] == 1, "invalidate restored item")
    require(
        invalidated["history"][-1]["kind"] == "invalidate",
        "invalidate audit entry",
    )

    reset, _ = client.request(
        "POST",
        f"{lookup_path(code)}/reset",
        payload={"actor": "CLI host"},
        host_token=token,
    )
    require(reset["room"]["remaining_count"] == 3, "reset restored pool")

    configured, _ = client.request(
        "PATCH",
        lookup_path(code),
        payload={
            "config": {
                "min": 10,
                "max": 12,
                "with_replacement": True,
                "draw_count": 2,
            },
            "draw_policy": "anyone",
        },
        host_token=token,
    )
    require(configured["room"]["draw_policy"] == "anyone", "policy update")

    exported, _ = client.request(
        "GET", f"{lookup_path(code)}/export?{urlencode({'format': 'json'})}"
    )
    require(bool(exported), "JSON history export")
    qr, content_type = client.request("GET", f"{lookup_path(code)}/qr.svg")
    require(isinstance(qr, bytes) and b"<svg" in qr[:500], "SVG QR response")
    require("xml" in content_type or "svg" in content_type, "SVG QR content type")

    ended, _ = client.request(
        "POST",
        f"{lookup_path(code)}/end",
        payload={"actor": "CLI host"},
        host_token=token,
    )
    require(ended["room"]["status"] == "ended", "room ended")
    print_json({"ok": True, "room_code": code, "checks": 12})


def add_host_action_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("room", help="room ID or short code")
    parser.add_argument("--actor", default="CLI host")
    parser.add_argument(
        "--host-token",
        help="room-scoped host token (or set RANDOM_DRAW_HOST_TOKEN)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="application origin (default: %(default)s)",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create a room")
    create.add_argument("--mode", choices=("numbers", "list", "coin", "dice"), required=True)
    create.add_argument("--host-name", default="CLI host")
    create.add_argument("--draw-policy", choices=("host_only", "anyone"), default="host_only")
    create.add_argument("--config", type=parse_json_object, default={})

    state = commands.add_parser("state", help="get canonical participant-safe state")
    state.add_argument("room")

    draw = commands.add_parser("draw", help="draw one or more results")
    add_host_action_arguments(draw)
    draw.add_argument("--count", type=int, default=1)

    configure = commands.add_parser("configure", help="update host-managed settings")
    configure.add_argument("room")
    configure.add_argument("--config", type=parse_json_object, required=True)
    configure.add_argument("--draw-policy", choices=("host_only", "anyone"))
    configure.add_argument("--host-token")

    for name in ("reset", "invalidate", "end"):
        add_host_action_arguments(commands.add_parser(name, help=f"{name} a room round"))

    export = commands.add_parser("export", help="export result/audit history")
    export.add_argument("room")
    export.add_argument("--format", choices=("json", "csv"), default="json")
    export.add_argument("--output", type=Path)

    qr = commands.add_parser("qr", help="download the room share QR as SVG")
    qr.add_argument("room")
    qr.add_argument("--output", type=Path, required=True)

    commands.add_parser(
        "smoke",
        help="run a mutating end-to-end scenario (local/disposable environments only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = ApiClient(args.base_url, args.timeout)
    try:
        if args.command == "smoke":
            run_smoke(args, client)
        else:
            run_command(args, client)
    except (ApiError, KeyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
