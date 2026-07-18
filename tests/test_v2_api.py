import json
from pathlib import Path

import pytest


def create_room(
    client,
    *,
    mode="numbers",
    config=None,
    draw_policy="host_only",
    host_name="Host",
):
    response = client.post(
        "/api/rooms",
        json={
            "mode": mode,
            "config": config
            or {"min": 1, "max": 3, "with_replacement": False, "draw_count": 1},
            "draw_policy": draw_policy,
            "host_name": host_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def host_headers(created):
    return {"X-Host-Token": created["host_token"]}


def test_solo_rest_draw_is_immediate_authoritative_and_recovers_on_reload(client):
    created = create_room(
        client,
        config={"min": 10, "max": 11, "with_replacement": False, "draw_count": 1},
        host_name="Solo host",
    )
    code = created["room"]["code"]

    first = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Solo host", "count": 1},
        headers=host_headers(created),
    )
    second = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Solo host", "count": 1},
        headers=host_headers(created),
    )
    assert first.status_code == second.status_code == 200
    results = {
        first.json()["room"]["latest_result"][0],
        second.json()["room"]["latest_result"][0],
    }
    assert results == {10, 11}
    assert second.json()["room"]["remaining_count"] == 0

    exhausted = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Solo host", "count": 1},
        headers=host_headers(created),
    )
    assert exhausted.status_code == 409

    restored = client.get(f"/api/rooms/{code}", headers=host_headers(created))
    assert restored.status_code == 200
    assert restored.json()["room"]["remaining_count"] == 0
    assert restored.json()["room"]["config"] == created["room"]["config"]
    assert [entry["draw_index"] for entry in restored.json()["history"]] == [1, 2]
    assert all(entry["receipt"]["pool_fingerprint"] for entry in restored.json()["history"])


def test_http_rejects_client_owned_pool_fields_without_mutating_state(client):
    created = create_room(
        client,
        config={"min": 5, "max": 5, "with_replacement": False, "draw_count": 1},
    )
    code = created["room"]["code"]

    rejected = client.post(
        f"/api/rooms/{code}/draw",
        json={
            "actor": "Host",
            "count": 1,
            "eligible_items": [999],
            "drawn_items": [5],
        },
        headers=host_headers(created),
    )
    assert rejected.status_code == 422
    unchanged = client.get(f"/api/rooms/{code}").json()
    assert unchanged["room"]["remaining_count"] == 1
    assert unchanged["history"] == []


@pytest.mark.parametrize("count", [True, 1.0, "1"])
def test_http_draw_rejects_coercible_non_integer_counts_without_mutating_state(client, count):
    created = create_room(client)
    code = created["room"]["code"]

    rejected = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Host", "count": count},
        headers=host_headers(created),
    )

    assert rejected.status_code == 422
    state = client.get(f"/api/rooms/{code}").json()
    assert state["room"]["remaining_count"] == 3
    assert state["history"] == []


def test_host_permissions_validation_and_safe_participant_state(client):
    created = create_room(client)
    code = created["room"]["code"]

    forbidden = client.post(
        f"/api/rooms/{code}/reset", json={"actor": "Not host"}
    )
    assert forbidden.status_code == 403
    assert "host" in forbidden.json()["detail"].lower()

    malformed = client.patch(
        f"/api/rooms/{code}",
        json={"config": {"min": 9, "max": 2}, "actor": "Host"},
        headers=host_headers(created),
    )
    assert malformed.status_code == 422

    updated = client.patch(
        f"/api/rooms/{code}",
        json={"draw_policy": "anyone", "actor": "Host"},
        headers={"Authorization": f"Bearer {created['host_token']}"},
    )
    assert updated.status_code == 200
    assert updated.json()["room"]["draw_policy"] == "anyone"
    guest_draw = client.post(
        f"/api/rooms/{code}/draw", json={"actor": "Guest", "count": 1}
    )
    assert guest_draw.status_code == 200
    assert guest_draw.json()["history"][-1]["actor"] == "Guest"

    participant_view = client.get(f"/api/rooms/{code}").json()
    serialized = json.dumps(participant_view)
    assert created["host_token"] not in serialized
    assert "host_token_hash" not in serialized
    assert participant_view["permissions"] == {
        "is_host": False,
        "can_draw": True,
        "can_manage": False,
    }


def test_short_code_lookup_is_human_friendly_and_case_insensitive(client):
    created = create_room(client)
    room = created["room"]

    by_code = client.get(f"/api/rooms/lookup/{room['code'].lower()}")
    by_id = client.get(f"/api/rooms/{room['id']}")
    assert by_code.status_code == by_id.status_code == 200
    assert by_code.json()["room"]["id"] == by_id.json()["room"]["id"]
    assert len(room["code"]) == 6
    assert room["code"] != room["id"]
    assert client.get("/api/rooms/lookup/UNKNOWN").status_code == 404


def test_invalidate_api_appends_audit_and_restores_no_replacement_item(client):
    created = create_room(
        client,
        config={"min": 1, "max": 1, "with_replacement": False, "draw_count": 1},
    )
    code = created["room"]["code"]
    drawn = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Host"},
        headers=host_headers(created),
    )
    assert drawn.json()["room"]["remaining_count"] == 0

    invalidated = client.post(
        f"/api/rooms/{code}/invalidate",
        json={"actor": "Host"},
        headers=host_headers(created),
    )
    assert invalidated.status_code == 200
    state = invalidated.json()
    assert state["room"]["remaining_count"] == 1
    assert [event["kind"] for event in state["history"]] == ["draw", "invalidate"]
    assert state["history"][0]["invalidated"] is True
    assert state["history"][1]["details"]["invalidated_draw_index"] == 1


def test_ended_room_is_readable_but_no_longer_actionable(client):
    created = create_room(client)
    code = created["room"]["code"]
    ended = client.post(
        f"/api/rooms/{code}/end",
        json={"actor": "Host"},
        headers=host_headers(created),
    )
    assert ended.status_code == 200
    assert ended.json()["room"]["status"] == "ended"
    assert ended.json()["history"][-1]["kind"] == "end"
    assert ended.json()["permissions"]["can_draw"] is False
    assert ended.json()["permissions"]["can_manage"] is False

    draw = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Host"},
        headers=host_headers(created),
    )
    assert draw.status_code == 409
    readable = client.get(f"/api/rooms/{code}")
    assert readable.status_code == 200
    assert readable.json()["room"]["status"] == "ended"


def test_two_clients_share_state_and_reconnect_to_full_canonical_history(client):
    created = create_room(
        client,
        config={"min": 5, "max": 5, "with_replacement": False, "draw_count": 1},
        draw_policy="anyone",
        host_name="Referee",
    )
    code = created["room"]["code"]
    host_url = f"/ws/room/{code}?client_id=host&name=Referee"
    guest_url = f"/ws/room/{code}?client_id=guest&name=Guest%20player"

    with client.websocket_connect(host_url) as host:
        initial = host.receive_json()
        assert initial["type"] == "state"
        assert initial["state"]["permissions"]["is_host"] is False
        host.send_json({"type": "auth", "host_token": created["host_token"]})
        authenticated = host.receive_json()
        assert authenticated["type"] == "state"
        assert authenticated["state"]["permissions"]["is_host"] is True

        with client.websocket_connect(guest_url) as guest:
            joined_for_host = host.receive_json()
            joined_for_guest = guest.receive_json()
            assert len(joined_for_host["state"]["participants"]) == 2
            assert joined_for_host["state"]["room"] == joined_for_guest["state"]["room"]
            assert [person["is_self"] for person in joined_for_host["state"]["participants"]] == [True, False]
            assert [person["is_self"] for person in joined_for_guest["state"]["participants"]] == [False, True]
            assert "client_id" not in json.dumps(joined_for_host["state"]["participants"])

            # Old clients used to provide these values. They must have no effect
            # on the authoritative eligible pool or persisted drawn markers.
            guest.send_json(
                {
                    "type": "draw",
                    "count": 1,
                    "eligible_items": [999],
                    "drawn_items": [5],
                }
            )
            host_draw = host.receive_json()
            guest_draw = guest.receive_json()
            assert host_draw["type"] == guest_draw["type"] == "state"
            assert host_draw["state"]["room"]["latest_result"] == [5]
            assert host_draw["state"]["room"] == guest_draw["state"]["room"]
            assert host_draw["state"]["history"] == guest_draw["state"]["history"]
            assert host_draw["state"]["room"]["remaining_count"] == 0

        left_state = host.receive_json()
        assert len(left_state["state"]["participants"]) == 1

        with client.websocket_connect(guest_url) as reconnected:
            host_rejoin = host.receive_json()
            recovered = reconnected.receive_json()
            assert len(host_rejoin["state"]["participants"]) == 2
            assert recovered["state"]["room"]["config"] == created["room"]["config"]
            assert recovered["state"]["room"]["remaining_count"] == 0
            assert recovered["state"]["room"]["latest_result"] == [5]
            assert len(recovered["state"]["history"]) == 1
            assert recovered["state"]["history"][0]["draw_index"] == 1


def test_team_presentation_metadata_survives_create_state_draw_and_reconnect(client):
    created = create_room(
        client,
        mode="list",
        config={
            "list_text": "Ada, Grace, Linus, Margaret",
            "with_replacement": False,
            "draw_count": 4,
            "presentation": "teams",
            "team_count": 2,
        },
        host_name="Referee",
    )
    code = created["room"]["code"]
    expected = {"presentation": "teams", "team_count": 2, "draw_count": 4}
    assert all(created["room"]["config"][key] == value for key, value in expected.items())

    loaded = client.get(f"/api/rooms/{code}").json()
    assert all(loaded["room"]["config"][key] == value for key, value in expected.items())

    draw = client.post(
        f"/api/rooms/{code}/draw",
        json={"actor": "Referee"},
        headers=host_headers(created),
    )
    assert draw.status_code == 200
    result = draw.json()["room"]["latest_result"]
    assert len(result) == len(set(result)) == 4
    assert set(result) == {"Ada", "Grace", "Linus", "Margaret"}
    details = draw.json()["history"][-1]["details"]
    assert details["presentation"] == "teams"
    assert details["team_count"] == 2
    assert details["config"]["presentation"] == "teams"

    ws_url = f"/ws/room/{code}?client_id=guest&name=Guest"
    with client.websocket_connect(ws_url) as first:
        first_state = first.receive_json()["state"]
        assert all(first_state["room"]["config"][key] == value for key, value in expected.items())
        assert first_state["room"]["latest_result"] == result
    with client.websocket_connect(ws_url) as reconnected:
        recovered = reconnected.receive_json()["state"]
        assert all(recovered["room"]["config"][key] == value for key, value in expected.items())
        assert recovered["room"]["latest_result"] == result
        assert recovered["history"][-1]["details"]["presentation"] == "teams"


def test_websocket_malformed_and_unknown_messages_are_safe_and_connection_survives(client):
    created = create_room(client, draw_policy="anyone")
    code = created["room"]["code"]

    with client.websocket_connect(f"/ws/room/{code}?client_id=guest&name=Guest") as ws:
        assert ws.receive_json()["type"] == "state"

        ws.send_text("{not json")
        malformed = ws.receive_json()
        assert malformed == {
            "type": "error",
            "error": {"status": 400, "code": 400, "message": "Message must be valid JSON"},
        }

        ws.send_json({"type": "does_not_exist", "debug": "do not reflect me"})
        unknown = ws.receive_json()
        assert unknown["type"] == "error"
        assert unknown["error"]["status"] == 422
        assert unknown["error"]["message"] == "Unknown message type"
        assert "debug" not in json.dumps(unknown)

        ws.send_json({"type": "heartbeat"})
        assert ws.receive_json() == {"type": "heartbeat_ack"}


def test_websocket_username_is_sanitized_bounded_and_shared_as_plain_data(client):
    created = create_room(client, draw_policy="anyone")
    code = created["room"]["code"]
    unsafe = "<img src=x onerror=alert(1)>\x00\u202e" + ("x" * 80)

    with client.websocket_connect(f"/ws/room/{code}?client_id=guest&name=Guest") as ws:
        ws.receive_json()
        ws.send_json({"type": "name_change", "username": unsafe})
        state = ws.receive_json()["state"]
        participant = state["participants"][0]
        assert participant["name"].startswith("<img src=x")
        assert len(participant["name"]) == 40
        assert "\x00" not in participant["name"]
        assert "\u202e" not in participant["name"]


def test_user_controlled_room_values_render_through_text_content_not_html():
    source = Path("app/static/js/room.js").read_text(encoding="utf-8")

    assert "function safeElement" in source
    assert "element.textContent = String(text)" in source
    assert 'safeElement("span", "participant-name", label)' in source
    assert 'safeElement("strong", "history-result", result)' in source
    assert "innerHTML" not in source


def test_room_client_preserves_presentation_and_mobile_accessibility_contracts():
    """Keep the client-only regressions visible without a browser-only test rig."""

    client_source = Path("app/static/js/room.js").read_text(encoding="utf-8")
    room_template = Path("app/templates/room.html").read_text(encoding="utf-8")
    room_css = Path("app/static/css/room.css").read_text(encoding="utf-8")

    # Draw receipts retain the settings active at their draw, and changing the
    # UI language rebuilds only generated field labels rather than ordinary
    # in-progress form state.
    assert "formatResult(event.result, event)" in client_source
    assert "populateSettings(state.room, Boolean(permissions.can_manage ?? isHost), true)" in client_source
    # Narrow headers hide visual copy, so the icon controls must remain named.
    assert 'setAttribute("aria-label", `${participants.length || 1} ${t("room.people")}`)' in client_source
    assert 'id="participants-button"' in room_template
    assert 'aria-label="Participants"' in room_template
    assert 'id="share-button"' in room_template
    assert 'aria-label="Share"' in room_template
    # Team/order strings deliberately include newlines; preserve them in the
    # oversized result slip instead of collapsing them into one unreadable row.
    assert "white-space: pre-line" in room_css
    # Historical results should not be announced during reconnect/presence
    # state refreshes, and the server only exposes a recipient-safe self flag.
    assert 'if (animate) elements.announcement.textContent' in client_source
    assert "const isYou = participant.is_self === true" in client_source


def test_home_client_rejects_bad_weights_and_associates_inline_errors():
    source = Path("app/static/js/home.js").read_text(encoding="utf-8")

    assert "weight < 1 || weight > 10000" in source
    assert 'if (parsedList?.invalidWeight)' in source
    assert 'field.setAttribute("aria-invalid", "true")' in source
    assert 'field.setAttribute("aria-describedby", "form-error")' in source
