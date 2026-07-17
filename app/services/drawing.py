"""Authoritative V2 room state, validation and cryptographic drawing logic."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
import hashlib
import hmac
import io
import json
import re
import secrets
import string
import threading
import unicodedata
import uuid
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.database import Log, Room, RoomEvent, utcnow

MODES = {"numbers", "list", "coin", "dice"}
DRAW_POLICIES = {"host_only", "anyone"}
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 6
MAX_LIST_ITEMS = 5_000
MAX_NUMBER_SPAN = 100_000
MAX_DRAW_COUNT = 100
MAX_TOTAL_WEIGHT = 1_000_000
DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    "numbers": {"min": 1, "max": 100, "with_replacement": False, "draw_count": 1},
    "list": {
        "items": [],
        "with_replacement": False,
        "draw_count": 1,
        "presentation": "plain",
    },
    "coin": {"draw_count": 1},
    "dice": {"dice_count": 1, "dice_sides": 6, "draw_count": 1},
}

_room_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def room_lock(room_id: str) -> threading.RLock:
    with _locks_guard:
        return _room_locks.setdefault(room_id, threading.RLock())


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def clean_actor(value: Any, *, default: str = "Guest") -> str:
    if not isinstance(value, str):
        return default
    # Strip control/format characters, collapse whitespace, and cap storage/UI.
    cleaned = "".join(
        char for char in value if unicodedata.category(char) not in {"Cc", "Cf"}
    )
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned[:40] or default


def normalize_mode(value: Any) -> str:
    aliases = {"number": "numbers", "names": "list", "names/list": "list"}
    mode = aliases.get(str(value).lower(), str(value).lower())
    if mode not in MODES:
        raise HTTPException(422, detail="Mode must be numbers, list, coin, or dice")
    return mode


def strict_int(value: Any, detail: str) -> int:
    if isinstance(value, bool):
        raise HTTPException(422, detail=detail)
    if isinstance(value, float) and not value.is_integer():
        raise HTTPException(422, detail=detail)
    if isinstance(value, str) and not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise HTTPException(422, detail=detail)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(422, detail=detail) from None


def strict_bool(value: Any, detail: str) -> bool:
    if not isinstance(value, bool):
        raise HTTPException(422, detail=detail)
    return value


def parse_list_input(raw: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Canonicalize pasted cells and explicit ``Name :: weight`` entries.

    Lines, commas and tabs delimit cells. Duplicate labels are removed
    case-insensitively while preserving the first spelling and order.
    """

    candidates: list[Any]
    if raw is None:
        candidates = []
    elif isinstance(raw, str):
        candidates = re.split(r"[\n\r,\t]+", raw)
    elif isinstance(raw, list):
        candidates = raw
    else:
        raise HTTPException(422, detail="List items must be text or an array")

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = 0
    blank_count = 0
    total_weight = 0
    for candidate in candidates:
        weight: Any = 1
        if isinstance(candidate, dict):
            label = candidate.get("value", candidate.get("label", ""))
            weight = candidate.get("weight", 1)
        else:
            label = str(candidate)
            if "::" in label:
                match = re.fullmatch(r"\s*(.*?)\s*::\s*(\d+)\s*", label)
                if not match:
                    raise HTTPException(422, detail="Weighted items must use Name :: positive whole number")
                label, weight = match.groups()
        label = " ".join(str(label).split()).strip()
        if not label:
            blank_count += 1
            continue
        if len(label) > 120:
            raise HTTPException(422, detail="List items must be 120 characters or fewer")
        weight = strict_int(weight, f"Invalid weight for {label!r}")
        if not 1 <= weight <= 10_000:
            raise HTTPException(422, detail="Weights must be whole numbers from 1 to 10000")
        key = label.casefold()
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        total_weight += weight
        if total_weight > MAX_TOTAL_WEIGHT:
            raise HTTPException(422, detail="Total list weight is too large")
        output.append({"value": label, "weight": weight})
        if len(output) > MAX_LIST_ITEMS:
            raise HTTPException(422, detail=f"Lists support at most {MAX_LIST_ITEMS} items")
    return output, {
        "input_count": len(candidates),
        "item_count": len(output),
        "duplicates_removed": duplicate_count,
        "blanks_removed": blank_count,
    }


def validate_config(mode: str, supplied: Any, current: dict[str, Any] | None = None) -> dict[str, Any]:
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise HTTPException(422, detail="Config must be an object")
    config = dict(DEFAULT_CONFIGS[mode] if current is None else current)
    config.update(supplied)
    default_count = config.get("draw_count", 1)
    config["draw_count"] = strict_int(default_count, "Draw count must be a whole number")
    if not 1 <= config["draw_count"] <= MAX_DRAW_COUNT:
        raise HTTPException(422, detail=f"Draw count must be between 1 and {MAX_DRAW_COUNT}")

    if mode == "numbers":
        config["min"] = strict_int(
            config.get("min", config.get("min_value", 1)),
            "Minimum and maximum must be whole numbers",
        )
        config["max"] = strict_int(
            config.get("max", config.get("max_value", 100)),
            "Minimum and maximum must be whole numbers",
        )
        if config["min"] > config["max"]:
            raise HTTPException(422, detail="Minimum cannot be greater than maximum")
        if config["max"] - config["min"] + 1 > MAX_NUMBER_SPAN:
            raise HTTPException(422, detail=f"Number range supports at most {MAX_NUMBER_SPAN} values")
        config["with_replacement"] = strict_bool(
            config.get("with_replacement", False), "With replacement must be true or false"
        )
        return {key: config[key] for key in ("min", "max", "with_replacement", "draw_count")}

    if mode == "list":
        raw_items = supplied.get("items", supplied.get("list_text", supplied.get("list_items")))
        if raw_items is None and current is not None:
            items = current.get("items", [])
            feedback = current.get("parsing", {"duplicates_removed": 0, "blanks_removed": 0})
        else:
            items, feedback = parse_list_input(raw_items)
        config["with_replacement"] = strict_bool(
            config.get("with_replacement", False), "With replacement must be true or false"
        )
        presentation = config.get("presentation", "plain")
        if not isinstance(presentation, str) or presentation not in {
            "plain",
            "winner",
            "order",
            "teams",
        }:
            raise HTTPException(
                422,
                detail="List presentation must be plain, winner, order, or teams",
            )
        canonical = {
            "items": items,
            "with_replacement": config["with_replacement"],
            "draw_count": config["draw_count"],
            "parsing": feedback,
            "presentation": presentation,
        }
        if presentation == "teams":
            team_count = strict_int(
                config.get("team_count", 2),
                "Team count must be a whole number from 2 to 20",
            )
            if not 2 <= team_count <= 20:
                raise HTTPException(422, detail="Team count must be between 2 and 20")
            canonical["team_count"] = team_count
        return canonical

    if mode == "dice":
        dice_count = strict_int(config.get("dice_count", 1), "Dice count and sides must be whole numbers")
        dice_sides = strict_int(
            config.get("dice_sides", config.get("sides", 6)),
            "Dice count and sides must be whole numbers",
        )
        if not 1 <= dice_count <= 20:
            raise HTTPException(422, detail="Dice count must be between 1 and 20")
        if not 2 <= dice_sides <= 1_000:
            raise HTTPException(422, detail="Dice sides must be between 2 and 1000")
        return {"dice_count": dice_count, "dice_sides": dice_sides, "draw_count": config["draw_count"]}

    return {"draw_count": config["draw_count"]}


def secure_index(upper_bound: int) -> int:
    """Return a uniform integer in ``range(upper_bound)`` using ``secrets``."""

    if not isinstance(upper_bound, int) or upper_bound <= 0:
        raise ValueError("upper_bound must be a positive integer")
    return secrets.randbelow(upper_bound)


def hash_host_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_host(room: Room, token: str | None) -> bool:
    return bool(
        token
        and room.host_token_hash
        and hmac.compare_digest(hash_host_token(token), room.host_token_hash)
    )


def require_host(room: Room, token: str | None) -> None:
    if not is_host(room, token):
        raise HTTPException(403, detail="This action is reserved for the room host")


def new_short_code(db: Session) -> str:
    for _ in range(100):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if db.query(Room.id).filter(Room.short_code == code).first() is None:
            return code
    raise HTTPException(503, detail="Could not allocate a room code; please try again")


def ensure_short_code(db: Session, room: Room) -> str:
    if room.short_code:
        return room.short_code
    room.short_code = new_short_code(db)
    db.flush()
    return room.short_code


def find_room(db: Session, lookup: str, *, for_update: bool = False) -> Room:
    lookup = str(lookup).strip()
    query = db.query(Room).filter(
        (Room.id == lookup) | (Room.short_code == lookup.upper())
    )
    if for_update:
        query = query.with_for_update()
    room = query.first()
    if room is None:
        raise HTTPException(404, detail="Room not found")
    ensure_short_code(db, room)
    if not room.mode:
        room.mode = "coin" if room.is_coin_flip else ("list" if room.is_list_draw else "numbers")
    if not room.config_json:
        legacy = {}
        if room.mode == "numbers":
            legacy = {
                "min": room.min_value if room.min_value is not None else 1,
                "max": room.max_value if room.max_value is not None else 100,
                "with_replacement": room.with_replacement if room.with_replacement is not None else True,
            }
        room.config_json = json_dump(validate_config(room.mode, legacy))
    room.drawn_json = room.drawn_json or "[]"
    room.draw_policy = room.draw_policy or "anyone"
    room.status = room.status or "active"
    room.draw_index = room.draw_index or 0
    room.event_index = room.event_index or 0
    room.round_index = room.round_index or 1
    if room.status == "active" and room.expires_at and room.expires_at <= utcnow():
        room.status = "expired"
        room.updated_at = utcnow()
    return room


def create_room(
    db: Session,
    *,
    mode: Any,
    config: Any = None,
    draw_policy: str = "host_only",
    host_name: Any = "Host",
) -> tuple[Room, str]:
    mode = normalize_mode(mode)
    if draw_policy not in DRAW_POLICIES:
        raise HTTPException(422, detail="Draw policy must be host_only or anyone")
    canonical = validate_config(mode, config)
    token = secrets.token_urlsafe(32)
    room = Room(
        id=str(uuid.uuid4()),
        short_code=new_short_code(db),
        mode=mode,
        config_json=json_dump(canonical),
        drawn_json="[]",
        host_token_hash=hash_host_token(token),
        host_name=clean_actor(host_name, default="Host"),
        draw_policy=draw_policy,
        status="active",
        draw_index=0,
        event_index=0,
        round_index=1,
        updated_at=utcnow(),
        expires_at=utcnow() + timedelta(days=30),
        is_coin_flip=mode == "coin",
        is_list_draw=mode == "list",
        min_value=canonical.get("min", 1),
        max_value=canonical.get("max", 100),
        with_replacement=canonical.get("with_replacement", True),
    )
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # An extraordinarily unlikely short-code collision at commit time.
        return create_room(
            db, mode=mode, config=config, draw_policy=draw_policy, host_name=host_name
        )
    db.refresh(room)
    return room, token


def eligible_pool(room: Room) -> list[Any]:
    config = json_load(room.config_json, DEFAULT_CONFIGS[room.mode])
    drawn = set(json_load(room.drawn_json, []))
    if room.mode == "numbers":
        return list(range(config["min"], config["max"] + 1))
    if room.mode == "list":
        return [item for item in config.get("items", [])]
    if room.mode == "coin":
        return ["Heads", "Tails"]
    return list(range(1, config.get("dice_sides", 6) + 1))


def remaining_pool(room: Room) -> list[Any]:
    config = json_load(room.config_json, DEFAULT_CONFIGS[room.mode])
    pool = eligible_pool(room)
    if config.get("with_replacement", True) or room.mode in {"coin", "dice"}:
        return pool
    drawn = set(json_load(room.drawn_json, []))
    if room.mode == "list":
        return [item for index, item in enumerate(pool) if index not in drawn]
    return [item for item in pool if item not in drawn]


def pool_fingerprint(pool: Iterable[Any]) -> str:
    """Concise SHA-256 fingerprint of the eligible pool before a draw.

    This is audit data, not a claim that the result was publicly verifiable.
    """

    return hashlib.sha256(json_dump(list(pool)).encode("utf-8")).hexdigest()


def _weighted_choice(items: list[dict[str, Any]]) -> int:
    total = sum(item.get("weight", 1) for item in items)
    target = secure_index(total)
    for index, item in enumerate(items):
        weight = item.get("weight", 1)
        if target < weight:
            return index
        target -= weight
    raise RuntimeError("weighted selection failed")


def _draw_one(room: Room, config: dict[str, Any], drawn: list[Any]) -> tuple[Any, Any | None]:
    """Return (display result, persisted no-replacement marker)."""

    if room.mode == "coin":
        return (["Heads", "Tails"][secure_index(2)], None)
    if room.mode == "dice":
        rolls = [secure_index(config["dice_sides"]) + 1 for _ in range(config["dice_count"])]
        return ({"rolls": rolls, "total": sum(rolls)}, None)
    if room.mode == "numbers":
        low, high = config["min"], config["max"]
        if config["with_replacement"]:
            return (low + secure_index(high - low + 1), None)
        drawn_set = set(int(value) for value in drawn)
        remaining = high - low + 1 - len(drawn_set)
        if remaining <= 0:
            raise HTTPException(409, detail="The round is complete; reset it to draw again")
        # Map a uniform index in the compact remaining range onto the original
        # range without allocating or randomly retrying near exhaustion.
        candidate = low + secure_index(remaining)
        for used in sorted(drawn_set):
            if used <= candidate:
                candidate += 1
            else:
                break
        return candidate, candidate
    items = config.get("items", [])
    if not items:
        raise HTTPException(409, detail="Add at least one list item before drawing")
    if config["with_replacement"]:
        index = _weighted_choice(items)
        return items[index]["value"], None
    drawn_set = set(int(value) for value in drawn)
    available = [(index, item) for index, item in enumerate(items) if index not in drawn_set]
    if not available:
        raise HTTPException(409, detail="The round is complete; reset it to draw again")
    local_index = _weighted_choice([item for _, item in available])
    original_index, selected = available[local_index]
    return selected["value"], original_index


def _append_event(
    db: Session,
    room: Room,
    *,
    kind: str,
    actor: str,
    result: Any = None,
    draw_index: int | None = None,
    fingerprint: str | None = None,
    pool_count: int | None = None,
    details: Any = None,
) -> RoomEvent:
    room.event_index = (room.event_index or 0) + 1
    event = RoomEvent(
        room_id=room.id,
        event_index=room.event_index,
        draw_index=draw_index,
        timestamp=utcnow(),
        kind=kind,
        mode=room.mode,
        actor=clean_actor(actor),
        result_json=json_dump(result) if result is not None else None,
        pool_fingerprint=fingerprint,
        pool_count=pool_count,
        details_json=json_dump(details) if details is not None else None,
        invalidated=False,
    )
    db.add(event)
    return event


def draw(db: Session, room: Room, *, token: str | None, actor: Any, count: Any = None) -> RoomEvent:
    with room_lock(room.id):
        room = find_room(db, room.id, for_update=True)
        if room.status != "active":
            raise HTTPException(409, detail=f"This room is {room.status}")
        if room.draw_policy == "host_only":
            require_host(room, token)
        config = json_load(room.config_json, DEFAULT_CONFIGS[room.mode])
        count = strict_int(
            config.get("draw_count", 1) if count is None else count,
            "Draw count must be a whole number",
        )
        if not 1 <= count <= MAX_DRAW_COUNT:
            raise HTTPException(422, detail=f"Draw count must be between 1 and {MAX_DRAW_COUNT}")
        before = remaining_pool(room)
        if room.mode in {"numbers", "list"} and not config.get("with_replacement", False):
            if not before:
                raise HTTPException(409, detail="The round is complete; reset it to draw again")
            if count > len(before):
                raise HTTPException(409, detail=f"Only {len(before)} item(s) remain in this round")
        fingerprint_payload: Any = before
        if room.mode == "dice":
            fingerprint_payload = [{"dice_count": config["dice_count"], "dice_sides": config["dice_sides"]}]
        fingerprint = pool_fingerprint(fingerprint_payload)
        drawn = list(json_load(room.drawn_json, []))
        results: list[Any] = []
        markers: list[Any] = []
        for _ in range(count):
            result, marker = _draw_one(room, config, drawn)
            results.append(result)
            if marker is not None:
                drawn.append(marker)
                markers.append(marker)
        room.drawn_json = json_dump(drawn)
        room.draw_index = (room.draw_index or 0) + 1
        room.latest_result_json = json_dump(results)
        room.updated_at = utcnow()
        event = _append_event(
            db,
            room,
            kind="draw",
            actor=clean_actor(actor),
            result=results,
            draw_index=room.draw_index,
            fingerprint=fingerprint,
            pool_count=len(before),
            details={
                "count": count,
                "round_index": room.round_index,
                "markers": markers,
                "config": config,
                "presentation": config.get("presentation") if room.mode == "list" else None,
                "team_count": config.get("team_count") if room.mode == "list" else None,
            },
        )
        db.add(
            Log(
                room_id=room.id,
                user_name=clean_actor(actor),
                action=f"{room.mode.title()} Draw",
                result=json_dump(results),
            )
        )
        db.commit()
        db.refresh(event)
        return event


def update_settings(
    db: Session,
    room: Room,
    *,
    token: str | None,
    config: Any = None,
    draw_policy: str | None = None,
    actor: Any = "Host",
    mode: Any = None,
) -> RoomEvent:
    with room_lock(room.id):
        room = find_room(db, room.id, for_update=True)
        require_host(room, token)
        if room.status != "active":
            raise HTTPException(409, detail=f"This room is {room.status}")
        target_mode = normalize_mode(mode) if mode is not None else room.mode
        current = json_load(room.config_json, DEFAULT_CONFIGS[target_mode]) if target_mode == room.mode else None
        canonical = validate_config(target_mode, config, current=current)
        if draw_policy is not None and draw_policy not in DRAW_POLICIES:
            raise HTTPException(422, detail="Draw policy must be host_only or anyone")
        # Any eligible-pool change starts a clean round; retaining markers would
        # make the new configuration's no-replacement state ambiguous.
        pool_changed = target_mode != room.mode or canonical != current
        room.mode = target_mode
        room.config_json = json_dump(canonical)
        room.is_coin_flip = target_mode == "coin"
        room.is_list_draw = target_mode == "list"
        room.min_value = canonical.get("min", room.min_value)
        room.max_value = canonical.get("max", room.max_value)
        room.with_replacement = canonical.get("with_replacement", True)
        if draw_policy is not None:
            room.draw_policy = draw_policy
        if pool_changed:
            room.drawn_json = "[]"
            room.latest_result_json = None
            room.round_index = (room.round_index or 1) + 1
        room.updated_at = utcnow()
        event = _append_event(
            db,
            room,
            kind="settings",
            actor=clean_actor(actor, default="Host"),
            details={"config": canonical, "draw_policy": room.draw_policy, "round_restarted": pool_changed},
        )
        db.commit()
        db.refresh(event)
        return event


def reset_round(db: Session, room: Room, *, token: str | None, actor: Any) -> RoomEvent:
    with room_lock(room.id):
        room = find_room(db, room.id, for_update=True)
        require_host(room, token)
        if room.status != "active":
            raise HTTPException(409, detail=f"This room is {room.status}")
        room.drawn_json = "[]"
        room.latest_result_json = None
        room.round_index = (room.round_index or 1) + 1
        room.updated_at = utcnow()
        event = _append_event(
            db, room, kind="reset", actor=clean_actor(actor, default="Host"), details={"round_index": room.round_index}
        )
        db.commit()
        db.refresh(event)
        return event


def invalidate_latest(db: Session, room: Room, *, token: str | None, actor: Any) -> RoomEvent:
    with room_lock(room.id):
        room = find_room(db, room.id, for_update=True)
        require_host(room, token)
        if room.status != "active":
            raise HTTPException(409, detail=f"This room is {room.status}")
        latest = (
            db.query(RoomEvent)
            .filter(
                RoomEvent.room_id == room.id,
                RoomEvent.kind == "draw",
                RoomEvent.invalidated.is_(False),
            )
            .order_by(RoomEvent.event_index.desc())
            .first()
        )
        if latest is None:
            raise HTTPException(409, detail="There is no result to invalidate")
        details = json_load(latest.details_json, {})
        if details.get("round_index") != room.round_index:
            raise HTTPException(409, detail="There is no result in the current round to invalidate")
        markers = details.get("markers", [])
        drawn = list(json_load(room.drawn_json, []))
        for marker in markers:
            try:
                drawn.remove(marker)
            except ValueError:
                pass
        room.drawn_json = json_dump(drawn)
        latest.invalidated = True
        previous_candidates = (
            db.query(RoomEvent)
            .filter(
                RoomEvent.room_id == room.id,
                RoomEvent.kind == "draw",
                RoomEvent.invalidated.is_(False),
                RoomEvent.id != latest.id,
            )
            .order_by(RoomEvent.event_index.desc())
            .all()
        )
        previous = next(
            (
                candidate
                for candidate in previous_candidates
                if json_load(candidate.details_json, {}).get("round_index") == room.round_index
            ),
            None,
        )
        room.latest_result_json = previous.result_json if previous else None
        room.updated_at = utcnow()
        event = _append_event(
            db,
            room,
            kind="invalidate",
            actor=clean_actor(actor, default="Host"),
            details={"invalidated_draw_index": latest.draw_index, "pool_restored": True},
        )
        db.commit()
        db.refresh(event)
        return event


def end_room(db: Session, room: Room, *, token: str | None, actor: Any) -> RoomEvent:
    with room_lock(room.id):
        room = find_room(db, room.id, for_update=True)
        require_host(room, token)
        if room.status != "active":
            raise HTTPException(409, detail=f"This room is {room.status}")
        room.status = "ended"
        room.ended_at = utcnow()
        room.updated_at = utcnow()
        event = _append_event(db, room, kind="end", actor=clean_actor(actor, default="Host"))
        db.commit()
        db.refresh(event)
        return event


def serialize_event(event: RoomEvent) -> dict[str, Any]:
    return {
        "event_index": event.event_index,
        "draw_index": event.draw_index,
        "timestamp": event.timestamp.isoformat() + ("Z" if event.timestamp.tzinfo is None else ""),
        "kind": event.kind,
        "mode": event.mode,
        "actor": event.actor,
        "result": json_load(event.result_json, None),
        "invalidated": bool(event.invalidated),
        "receipt": {
            "pool_fingerprint": event.pool_fingerprint,
            "pool_count": event.pool_count,
            "note": "SHA-256 fingerprint of the eligible pool before selection; not a proof of publicly verifiable randomness.",
        }
        if event.kind == "draw"
        else None,
        "details": json_load(event.details_json, None),
    }


def serialize_state(
    db: Session,
    room: Room,
    *,
    token: str | None = None,
    participants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ensure_short_code(db, room)
    config = json_load(room.config_json, DEFAULT_CONFIGS.get(room.mode, {}))
    drawn = set(json_load(room.drawn_json, []))
    if room.mode == "numbers":
        total_count = config["max"] - config["min"] + 1
        remaining_count = total_count if config.get("with_replacement", False) else total_count - len(drawn)
        visible_eligible = None
        visible_remaining = None
    elif room.mode == "list":
        visible_eligible = config.get("items", [])
        total_count = len(visible_eligible)
        if config.get("with_replacement", False):
            remaining_items = visible_eligible
        else:
            remaining_items = [item for index, item in enumerate(visible_eligible) if index not in drawn]
        remaining_count = len(remaining_items)
        visible_remaining = remaining_items
    elif room.mode == "coin":
        total_count = remaining_count = 2
        visible_eligible = visible_remaining = None
    else:
        total_count = remaining_count = config.get("dice_sides", 6)
        visible_eligible = visible_remaining = None
    host = is_host(room, token)
    events = (
        db.query(RoomEvent)
        .filter(RoomEvent.room_id == room.id)
        .order_by(RoomEvent.event_index.asc())
        .all()
    )
    state = {
        "room": {
            "id": room.id,
            "code": room.short_code,
            "mode": room.mode,
            "status": room.status,
            "config": config,
            "eligible_items": visible_eligible,
            "remaining_items": visible_remaining,
            "remaining_count": remaining_count,
            "total_count": total_count,
            "draw_policy": room.draw_policy,
            "round_index": room.round_index or 1,
            "latest_result": json_load(room.latest_result_json, None),
            "host_name": room.host_name or "Host",
            "created_at": room.created_at.isoformat() + "Z" if room.created_at else None,
            "updated_at": room.updated_at.isoformat() + "Z" if room.updated_at else None,
            "ended_at": room.ended_at.isoformat() + "Z" if room.ended_at else None,
            "expires_at": room.expires_at.isoformat() + "Z" if room.expires_at else None,
        },
        "history": [serialize_event(event) for event in events],
        "participants": participants or [],
        "permissions": {
            "is_host": host,
            "can_draw": room.status == "active" and (room.draw_policy == "anyone" or host),
            "can_manage": room.status == "active" and host,
        },
    }
    db.commit()  # persist an assigned short code for migrated rooms
    return state


def export_history_csv(events: list[RoomEvent]) -> str:
    def safe_cell(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["event_index", "draw_index", "timestamp", "kind", "mode", "actor", "result", "invalidated", "pool_fingerprint", "pool_count"]
    )
    for event in events:
        writer.writerow(
            [event.event_index, event.draw_index or "", event.timestamp.isoformat(), event.kind, event.mode, safe_cell(event.actor),
             safe_cell(json.dumps(json_load(event.result_json, None), ensure_ascii=False)), event.invalidated,
             event.pool_fingerprint or "", event.pool_count if event.pool_count is not None else ""]
        )
    return buffer.getvalue()
