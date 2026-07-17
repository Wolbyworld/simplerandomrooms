import json

import pytest

from scripts import random_draw_smoke


def test_cli_parser_accepts_structured_create_configuration():
    args = random_draw_smoke.build_parser().parse_args(
        [
            "--base-url",
            "http://localhost:9999/",
            "create",
            "--mode",
            "list",
            "--config",
            '{"items":[{"value":"Ada","weight":2}]}',
        ]
    )

    assert args.base_url == "http://localhost:9999/"
    assert args.config == {"items": [{"value": "Ada", "weight": 2}]}


def test_cli_parser_rejects_non_object_configuration():
    with pytest.raises(SystemExit):
        random_draw_smoke.build_parser().parse_args(
            ["create", "--mode", "numbers", "--config", "[1,2]"]
        )


def test_lookup_path_strips_and_encodes_user_input():
    assert random_draw_smoke.lookup_path(" AB/CD ") == "/api/rooms/AB%2FCD"


def test_host_token_can_come_from_scoped_environment(monkeypatch):
    args = random_draw_smoke.build_parser().parse_args(
        ["reset", "ABCD", "--actor", "Test host"]
    )
    monkeypatch.setenv("RANDOM_DRAW_HOST_TOKEN", "room-scoped-token")

    assert random_draw_smoke.token_from(args) == "room-scoped-token"


def test_main_returns_nonzero_and_prints_safe_api_error(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise random_draw_smoke.ApiError("GET /health: connection refused")

    monkeypatch.setattr(random_draw_smoke, "run_smoke", fail)

    assert random_draw_smoke.main(["smoke"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GET /health: connection refused\n"


def test_main_routes_smoke_to_configured_api_client(monkeypatch, capsys):
    observed = {}

    def fake_smoke(args, client):
        observed.update(base_url=client.base_url, timeout=client.timeout)
        print(json.dumps({"ok": True}))

    monkeypatch.setattr(random_draw_smoke, "run_smoke", fake_smoke)

    assert (
        random_draw_smoke.main(
            ["--base-url", "http://127.0.0.1:8765/", "--timeout", "2", "smoke"]
        )
        == 0
    )
    assert observed == {"base_url": "http://127.0.0.1:8765", "timeout": 2.0}
    assert json.loads(capsys.readouterr().out) == {"ok": True}
