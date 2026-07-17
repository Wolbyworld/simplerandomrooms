import csv
import io
import sqlite3
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import database
from app.models.database import Base, Room, RoomEvent, utcnow
from app.services import drawing


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_room(db, **overrides):
    values = {
        "mode": "numbers",
        "config": {
            "min": 1,
            "max": 3,
            "with_replacement": False,
            "draw_count": 1,
        },
        "draw_policy": "host_only",
        "host_name": "Host",
    }
    values.update(overrides)
    return drawing.create_room(db, **values)


def test_secure_index_uses_unbiased_randbelow_boundaries(monkeypatch):
    seen = []

    def last_value(upper_bound):
        seen.append(upper_bound)
        return upper_bound - 1

    monkeypatch.setattr(drawing.secrets, "randbelow", last_value)

    assert drawing.secure_index(1) == 0
    assert drawing.secure_index(17) == 16
    assert seen == [1, 17]
    for invalid in (0, -1, 1.5, "3"):
        with pytest.raises(ValueError, match="positive integer"):
            drawing.secure_index(invalid)


def test_number_draw_maps_randbelow_first_and_last_values_to_inclusive_bounds(db, monkeypatch):
    room, token = make_room(
        db,
        config={"min": -4, "max": 4, "with_replacement": True, "draw_count": 1},
    )
    values = iter([0, 8])
    monkeypatch.setattr(drawing, "secure_index", lambda upper: next(values))

    first = drawing.draw(db, room, token=token, actor="Host")
    second = drawing.draw(db, room, token=token, actor="Host")

    assert drawing.json_load(first.result_json, None) == [-4]
    assert drawing.json_load(second.result_json, None) == [4]


def test_list_parser_canonicalizes_delimiters_deduplicates_and_keeps_weights():
    items, feedback = drawing.parse_list_input(
        "  Ada Lovelace,Grace Hopper\tada lovelace\nLinus Torvalds :: 3\n"
    )

    assert items == [
        {"value": "Ada Lovelace", "weight": 1},
        {"value": "Grace Hopper", "weight": 1},
        {"value": "Linus Torvalds", "weight": 3},
    ]
    assert feedback["item_count"] == 3
    assert feedback["duplicates_removed"] == 1
    assert feedback["blanks_removed"] >= 1


@pytest.mark.parametrize("weight", [0, -1, 10_001, "heavy"])
def test_list_parser_rejects_invalid_explicit_weights(weight):
    with pytest.raises(HTTPException) as error:
        drawing.parse_list_input([{"value": "Ada", "weight": weight}])
    assert error.value.status_code == 422


@pytest.mark.parametrize("raw", ["Ada :: -1", "Ada :: 1.5", "Ada :: heavy"])
def test_list_parser_rejects_malformed_weight_syntax(raw):
    with pytest.raises(HTTPException) as error:
        drawing.parse_list_input(raw)
    assert error.value.status_code == 422
    assert "weight" in error.value.detail.lower()


def test_list_parser_preserves_first_seen_spelling_and_weight():
    items, feedback = drawing.parse_list_input(
        [
            {"value": "ALICE", "weight": 2},
            {"value": "alice", "weight": 9},
            {"label": " Bob ", "weight": 1},
        ]
    )

    assert items == [
        {"value": "ALICE", "weight": 2},
        {"value": "Bob", "weight": 1},
    ]
    assert feedback["duplicates_removed"] == 1


def test_list_parser_removes_control_and_bidi_format_characters_before_storage():
    items, _feedback = drawing.parse_list_input(
        ["Ada\u202e", {"value": "\x00Grace\u2066 Hopper", "weight": 2}]
    )

    assert items == [
        {"value": "Ada", "weight": 1},
        {"value": "Grace Hopper", "weight": 2},
    ]


def test_no_replacement_exhaustion_is_persisted(db, monkeypatch):
    room, token = make_room(
        db,
        config={"min": 4, "max": 5, "with_replacement": False, "draw_count": 1},
    )
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)

    first = drawing.draw(db, room, token=token, actor="Host")
    db.expire_all()
    reloaded = drawing.find_room(db, room.id)
    second = drawing.draw(db, reloaded, token=token, actor="Host")

    assert drawing.json_load(first.result_json, None) == [4]
    assert drawing.json_load(second.result_json, None) == [5]
    db.expire_all()
    exhausted = drawing.find_room(db, room.id)
    assert drawing.remaining_pool(exhausted) == []
    with pytest.raises(HTTPException) as error:
        drawing.draw(db, exhausted, token=token, actor="Host")
    assert error.value.status_code == 409
    assert "complete" in error.value.detail.lower()


def test_multiple_winners_are_atomic_and_unique_without_replacement(db, monkeypatch):
    room, token = make_room(db)
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)

    event = drawing.draw(db, room, token=token, actor="Host", count=3)
    assert drawing.json_load(event.result_json, None) == [1, 2, 3]
    assert drawing.remaining_pool(drawing.find_room(db, room.id)) == []

    room2, token2 = make_room(
        db,
        config={"min": 1, "max": 2, "with_replacement": False, "draw_count": 1},
    )
    with pytest.raises(HTTPException) as error:
        drawing.draw(db, room2, token=token2, actor="Host", count=3)
    assert error.value.status_code == 409
    assert db.query(RoomEvent).filter(RoomEvent.room_id == room2.id).count() == 0
    assert drawing.remaining_pool(room2) == [1, 2]


def test_weighted_list_no_replacement_persists_and_exhausts(db, monkeypatch):
    room, token = make_room(
        db,
        mode="list",
        config={
            "items": [
                {"value": "Ada", "weight": 3},
                {"value": "Grace", "weight": 1},
            ],
            "with_replacement": False,
            "draw_count": 1,
        },
    )
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)

    first = drawing.draw(db, room, token=token, actor="Host")
    db.expire_all()
    second = drawing.draw(
        db, drawing.find_room(db, room.id), token=token, actor="Host"
    )
    assert drawing.json_load(first.result_json, None) == ["Ada"]
    assert drawing.json_load(second.result_json, None) == ["Grace"]
    assert drawing.remaining_pool(drawing.find_room(db, room.id)) == []
    with pytest.raises(HTTPException) as error:
        drawing.draw(db, room, token=token, actor="Host")
    assert error.value.status_code == 409
    assert "reset" in error.value.detail.lower()


@pytest.mark.parametrize(
    ("presentation", "team_count"),
    [("order", None), ("teams", 2)],
)
def test_order_and_teams_draw_every_canonical_list_item_once(
    db, monkeypatch, presentation, team_count
):
    config = {
        "list_text": "Ada, Grace, Linus, Margaret",
        "with_replacement": False,
        "draw_count": 4,
        "presentation": presentation,
    }
    if team_count is not None:
        config["team_count"] = team_count
    room, token = make_room(db, mode="list", config=config)
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)

    event = drawing.draw(db, room, token=token, actor="Host")
    result = drawing.json_load(event.result_json, None)
    details = drawing.json_load(event.details_json, None)
    state = drawing.serialize_state(db, drawing.find_room(db, room.id), token=token)

    assert len(result) == len(set(result)) == 4
    assert set(result) == {"Ada", "Grace", "Linus", "Margaret"}
    assert state["room"]["remaining_count"] == 0
    assert state["room"]["config"]["presentation"] == presentation
    assert details["presentation"] == presentation
    assert details["team_count"] == team_count
    assert details["config"]["draw_count"] == 4
    if presentation == "teams":
        assert state["room"]["config"]["team_count"] == 2
    else:
        assert "team_count" not in state["room"]["config"]


def test_host_permissions_and_anyone_can_draw_policy(db):
    room, token = make_room(db)

    with pytest.raises(HTTPException) as error:
        drawing.draw(db, room, token=None, actor="Guest")
    assert error.value.status_code == 403
    assert db.query(RoomEvent).filter(RoomEvent.room_id == room.id).count() == 0

    drawing.update_settings(
        db,
        room,
        token=token,
        config=None,
        draw_policy="anyone",
        actor="Host",
    )
    event = drawing.draw(db, room, token=None, actor="Guest")
    assert event.actor == "Guest"

    for action in (
        lambda: drawing.update_settings(db, room, token=None, config={"max": 2}),
        lambda: drawing.reset_round(db, room, token=None, actor="Guest"),
        lambda: drawing.invalidate_latest(db, room, token=None, actor="Guest"),
        lambda: drawing.end_room(db, room, token=None, actor="Guest"),
    ):
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 403

    other_room, other_token = make_room(db)
    assert other_token != token
    with pytest.raises(HTTPException) as error:
        drawing.reset_round(db, other_room, token=token, actor="Wrong room")
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    ("mode", "config", "detail"),
    [
        ("numbers", {"min": 3, "max": 2}, "greater"),
        ("numbers", {"min": 0, "max": drawing.MAX_NUMBER_SPAN}, "at most"),
        ("numbers", {"draw_count": 0}, "between"),
        ("dice", {"dice_count": 0, "dice_sides": 6}, "dice count"),
        ("dice", {"dice_count": 1, "dice_sides": 1}, "sides"),
        ("list", {"items": "", "draw_count": drawing.MAX_DRAW_COUNT + 1}, "between"),
        ("list", {"items": "Ada,Bob", "presentation": "bracket"}, "presentation"),
        ("list", {"items": "Ada,Bob", "presentation": "teams", "team_count": 1}, "team count"),
    ],
)
def test_configuration_validation_is_bounded(mode, config, detail):
    with pytest.raises(HTTPException) as error:
        drawing.validate_config(mode, config)
    assert error.value.status_code == 422
    assert detail in error.value.detail.lower()


def test_username_canonicalization_removes_controls_caps_length_and_is_not_html(db):
    actor = "  <img src=x onerror=alert(1)>\x00\n\u202e  " + ("x" * 80)
    cleaned = drawing.clean_actor(actor)

    assert "\x00" not in cleaned
    assert "\u202e" not in cleaned
    assert "\n" not in cleaned
    assert len(cleaned) == 40
    assert cleaned.startswith("<img src=x")

    room, token = make_room(db, host_name=actor)
    assert room.host_name == cleaned
    event = drawing.draw(db, room, token=token, actor=actor)
    assert event.actor == cleaned


def test_invalidate_is_append_only_and_restores_latest_pool_item(db, monkeypatch):
    room, token = make_room(db)
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)
    draw_event = drawing.draw(db, room, token=token, actor="Host")
    original_fingerprint = draw_event.pool_fingerprint

    invalidation = drawing.invalidate_latest(db, room, token=token, actor="Host")
    db.refresh(draw_event)
    state = drawing.serialize_state(db, drawing.find_room(db, room.id), token=token)

    assert draw_event.invalidated is True
    assert draw_event.pool_fingerprint == original_fingerprint
    assert invalidation.kind == "invalidate"
    assert drawing.json_load(invalidation.details_json, {}) == {
        "invalidated_draw_index": 1,
        "pool_restored": True,
    }
    assert state["room"]["remaining_count"] == 3
    assert [event["kind"] for event in state["history"]] == ["draw", "invalidate"]
    assert state["history"][0]["invalidated"] is True


def test_invalidate_never_reaches_back_across_a_reset_boundary(db, monkeypatch):
    room, token = make_room(db)
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 0)
    drawing.draw(db, room, token=token, actor="Host")
    drawing.reset_round(db, room, token=token, actor="Host")

    with pytest.raises(HTTPException) as error:
        drawing.invalidate_latest(db, room, token=token, actor="Host")
    assert error.value.status_code == 409
    assert "current round" in error.value.detail.lower()
    events = db.query(RoomEvent).filter(RoomEvent.room_id == room.id).all()
    assert [event.kind for event in events] == ["draw", "reset"]
    assert events[0].invalidated is False


def test_short_code_lookup_is_case_insensitive_and_internal_id_remains_distinct(db):
    room, _token = make_room(db)
    assert len(room.short_code) == drawing.CODE_LENGTH
    assert room.short_code != room.id

    assert drawing.find_room(db, f"  {room.short_code.lower()}  ").id == room.id
    assert drawing.find_room(db, room.id).short_code == room.short_code
    with pytest.raises(HTTPException) as error:
        drawing.find_room(db, "not-a-room")
    assert error.value.status_code == 404


def test_expired_room_state_is_canonical_and_disables_actions(db):
    room, token = make_room(db)
    room.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    expired = drawing.find_room(db, room.id)
    state = drawing.serialize_state(db, expired, token=token)
    assert expired.status == "expired"
    assert state["room"]["status"] == "expired"
    assert state["permissions"] == {
        "is_host": True,
        "can_draw": False,
        "can_manage": False,
    }
    with pytest.raises(HTTPException) as error:
        drawing.draw(db, expired, token=token, actor="Host")
    assert error.value.status_code == 409


def test_pool_receipt_commits_to_pre_draw_eligible_pool(db, monkeypatch):
    room, token = make_room(db)
    expected = drawing.pool_fingerprint([1, 2, 3])
    monkeypatch.setattr(drawing, "secure_index", lambda _upper: 1)

    event = drawing.draw(db, room, token=token, actor="Host")
    serialized = drawing.serialize_event(event)

    assert event.pool_fingerprint == expected
    assert event.pool_count == 3
    assert serialized["receipt"]["pool_fingerprint"] == expected
    assert "not a proof" in serialized["receipt"]["note"]


@pytest.mark.parametrize("actor", ["=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "  =1+1"])
def test_csv_export_neutralizes_spreadsheet_formula_actors(db, actor):
    room, token = make_room(db)
    drawing.draw(db, room, token=token, actor=actor)
    events = db.query(RoomEvent).filter(RoomEvent.room_id == room.id).all()

    rows = list(csv.DictReader(io.StringIO(drawing.export_history_csv(events))))
    assert rows[0]["actor"].startswith("'")
    assert rows[0]["actor"][1:] == drawing.clean_actor(actor)


def test_additive_migration_preserves_legacy_room_and_log(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE rooms (
          id VARCHAR PRIMARY KEY,
          created_at DATETIME,
          is_coin_flip BOOLEAN,
          min_value INTEGER,
          max_value INTEGER,
          with_replacement BOOLEAN
        );
        CREATE TABLE logs (
          id INTEGER PRIMARY KEY,
          room_id VARCHAR,
          timestamp DATETIME,
          user_name VARCHAR,
          action VARCHAR,
          result VARCHAR
        );
        INSERT INTO rooms VALUES ('legacy-room', CURRENT_TIMESTAMP, 0, 7, 9, 0);
        INSERT INTO logs VALUES (1, 'legacy-room', CURRENT_TIMESTAMP, 'Ada', 'Number Draw', '8');
        """
    )
    connection.commit()
    connection.close()

    migrated_engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", migrated_engine)
    database.create_tables()

    columns = {column["name"] for column in inspect(migrated_engine).get_columns("rooms")}
    assert {"short_code", "config_json", "drawn_json", "host_token_hash"} <= columns
    assert "room_events" in inspect(migrated_engine).get_table_names()
    row = migrated_engine.connect().exec_driver_sql(
        "SELECT id, min_value, max_value, draw_policy, status FROM rooms"
    ).one()
    assert tuple(row) == ("legacy-room", 7, 9, "anyone", "active")
    log_count = migrated_engine.connect().exec_driver_sql("SELECT COUNT(*) FROM logs").scalar_one()
    assert log_count == 1
    migrated_engine.dispose()
