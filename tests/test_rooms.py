import re

from app.models.database import Room, SessionLocal


def test_legacy_create_coin_room_redirects_to_short_code_and_preserves_host_token(client):
    response = client.post(
        "/create-room",
        data={"is_coin_flip": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    match = re.fullmatch(r"/room/([2-9A-HJ-NP-Z]{6})#host=([A-Za-z0-9_-]+)", location)
    assert match is not None

    room_response = client.get(f"/room/{match.group(1)}")
    assert room_response.status_code == 200
    assert "result-stage" in room_response.text
    assert "draw-button" in room_response.text
    assert "participants-dialog" in room_response.text


def test_legacy_create_number_room_loads_v2_room(client):
    response = client.post(
        "/create-room",
        data={"is_coin_flip": "false"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    match = re.fullmatch(
        r"/room/([2-9A-HJ-NP-Z]{6})#host=([A-Za-z0-9_-]+)",
        response.headers["location"],
    )
    assert match is not None

    room_response = client.get(f"/room/{match.group(1)}")
    assert room_response.status_code == 200
    assert "Room settings" in room_response.text
    assert 'data-room-code="' + match.group(1) + '"' in room_response.text


def test_direct_v1_room_page_persists_its_lazily_assigned_short_code(client):
    """A V1 UUID route must not render a short code that vanishes on close."""

    with SessionLocal() as db:
        db.add(
            Room(
                id="legacy-room-without-code",
                is_coin_flip=False,
                min_value=7,
                max_value=9,
                with_replacement=False,
            )
        )
        db.commit()

    page = client.get("/room/legacy-room-without-code")
    assert page.status_code == 200
    match = re.search(r'data-room-code="([2-9A-HJ-NP-Z]{6})"', page.text)
    assert match is not None

    state = client.get(f"/api/rooms/{match.group(1)}")
    assert state.status_code == 200
    assert state.json()["room"]["id"] == "legacy-room-without-code"


def test_result_announcement_is_polite_for_screen_reader_users(client):
    response = client.post("/create-room", follow_redirects=False)
    room_response = client.get(response.headers["location"].split("#", 1)[0])

    assert 'id="result-announcement"' in room_response.text
    assert 'aria-live="polite"' in room_response.text
