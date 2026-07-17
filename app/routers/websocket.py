"""Presence, reconnect and authoritative room action WebSocket protocol."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.models.database import SessionLocal, get_db
from app.services import drawing

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_rooms: dict[str, dict[str, WebSocket]] = {}
        self.user_names: dict[str, dict[str, str]] = {}
        self.host_tokens: dict[str, dict[str, str | None]] = {}
        self.last_activity: dict[str, dict[str, datetime]] = {}
        self.inactivity_timeout = 10 * 60

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        client_id: str,
        name: str,
        token: str | None,
    ) -> bool:
        # A client id is a reconnect handle, not an identity proof. Never let a
        # second connection evict a live participant that happens to use the
        # same id. Refreshes naturally retry after the old socket closes.
        if room_id in self.active_rooms and client_id in self.active_rooms[room_id]:
            await websocket.close(code=1008, reason="Client id is already connected")
            return False
        await websocket.accept()
        self.active_rooms.setdefault(room_id, {})
        self.user_names.setdefault(room_id, {})
        self.host_tokens.setdefault(room_id, {})
        self.last_activity.setdefault(room_id, {})
        self.active_rooms[room_id][client_id] = websocket
        self.user_names[room_id][client_id] = drawing.clean_actor(name)
        self.host_tokens[room_id][client_id] = token
        self.last_activity[room_id][client_id] = datetime.utcnow()
        return True

    def disconnect(self, room_id: str, client_id: str, websocket: WebSocket | None = None) -> bool:
        connections = self.active_rooms.get(room_id)
        if not connections or client_id not in connections:
            return False
        if websocket is not None and connections[client_id] is not websocket:
            return False  # a newer reconnect has replaced this socket
        del connections[client_id]
        for mapping in (self.user_names, self.host_tokens, self.last_activity):
            mapping.get(room_id, {}).pop(client_id, None)
        if not connections:
            for mapping in (self.active_rooms, self.user_names, self.host_tokens, self.last_activity):
                mapping.pop(room_id, None)
        return True

    def get_users(
        self,
        room_id: str,
        room: Any | None = None,
        viewer_client_id: str | None = None,
    ) -> list[dict[str, Any]]:
        users = []
        for client_id, username in self.user_names.get(room_id, {}).items():
            token = self.host_tokens.get(room_id, {}).get(client_id)
            users.append(
                {
                    # Do not disclose the reconnect handle to other
                    # participants. Names and host status are sufficient for
                    # the presence UI and avoid a socket-takeover primitive.
                    "name": username,
                    "username": username,  # V1 compatibility
                    "is_host": drawing.is_host(room, token) if room is not None else False,
                    # This recipient-specific boolean supports a clear
                    # presence UI without exposing reconnect handles.
                    "is_self": client_id == viewer_client_id,
                    "connected": True,
                }
            )
        return users

    async def send_error(self, websocket: WebSocket, status: int, message: str) -> None:
        await websocket.send_json(
            {"type": "error", "error": {"status": status, "code": status, "message": message}}
        )

    async def broadcast_state(self, room_id: str) -> None:
        connections = list(self.active_rooms.get(room_id, {}).items())
        if not connections:
            return
        disconnected: list[tuple[str, WebSocket]] = []
        with SessionLocal() as db:
            try:
                room = drawing.find_room(db, room_id)
            except Exception:
                return
            for client_id, websocket in connections:
                try:
                    token = self.host_tokens.get(room_id, {}).get(client_id)
                    participants = self.get_users(room_id, room, client_id)
                    state = drawing.serialize_state(db, room, token=token, participants=participants)
                    await websocket.send_json({"type": "state", "state": state})
                except Exception:
                    disconnected.append((client_id, websocket))
        for client_id, websocket in disconnected:
            self.disconnect(room_id, client_id, websocket)

    async def broadcast_to_room(self, room_id: str, message: dict[str, Any]) -> None:
        # Retained for the disconnect beacon and older clients.
        for client_id, websocket in list(self.active_rooms.get(room_id, {}).items()):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(room_id, client_id, websocket)

    async def update_username(self, room_id: str, client_id: str, username: Any) -> None:
        if client_id not in self.user_names.get(room_id, {}):
            return
        self.user_names[room_id][client_id] = drawing.clean_actor(username)
        await self.broadcast_state(room_id)

    def update_activity(self, room_id: str, client_id: str) -> None:
        if client_id in self.last_activity.get(room_id, {}):
            self.last_activity[room_id][client_id] = datetime.utcnow()

    async def cleanup_inactive_connections(self) -> int:
        now = datetime.utcnow()
        removed = 0
        changed_rooms: set[str] = set()
        for room_id, activities in list(self.last_activity.items()):
            for client_id, last_active in list(activities.items()):
                if (now - last_active).total_seconds() <= self.inactivity_timeout:
                    continue
                websocket = self.active_rooms.get(room_id, {}).get(client_id)
                if websocket:
                    try:
                        await websocket.close(code=1001, reason="Connection timed out")
                    except Exception:
                        pass
                if self.disconnect(room_id, client_id, websocket):
                    removed += 1
                    changed_rooms.add(room_id)
        for room_id in changed_rooms:
            await self.broadcast_state(room_id)
        return removed


manager = ConnectionManager()


def _client_id(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 64 or not all(char.isalnum() or char in "-_" for char in value):
        raise ValueError("Invalid client id")
    return value


@router.websocket("/ws/room/{lookup}")
async def websocket_endpoint(
    websocket: WebSocket,
    lookup: str,
    client_id: str,
    name: str = "Guest",
    db: Session = Depends(get_db),
):
    try:
        client_id = _client_id(client_id)
        room = drawing.find_room(db, lookup)
    except Exception:
        await websocket.close(code=1008, reason="Invalid room or client id")
        return
    room_id = room.id
    # Browser WebSocket APIs cannot set custom auth headers. Keep the room
    # credential out of URLs (and therefore access logs/referrers): hosts send
    # it in their first ``auth`` message after the participant-safe state.
    if not await manager.connect(websocket, room_id, client_id, name, None):
        return
    await manager.broadcast_state(room_id)
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 65_536:
                await manager.send_error(websocket, 1009, "Message is too large")
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_error(websocket, 400, "Message must be valid JSON")
                continue
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                await manager.send_error(websocket, 422, "Message type is required")
                continue
            manager.update_activity(room_id, client_id)
            kind = message["type"]
            if kind == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack"})
                continue
            if kind == "disconnect":
                break
            if kind == "auth":
                token = message.get("host_token")
                if token is not None and not isinstance(token, str):
                    await manager.send_error(websocket, 422, "Host token must be text")
                    continue
                manager.host_tokens[room_id][client_id] = token
                await manager.broadcast_state(room_id)
                continue
            if kind == "name_change":
                await manager.update_username(room_id, client_id, message.get("username", message.get("name")))
                continue
            try:
                db.expire_all()
                room = drawing.find_room(db, room_id)
                token = manager.host_tokens.get(room_id, {}).get(client_id)
                actor = manager.user_names.get(room_id, {}).get(client_id, "Guest")
                if kind in {"draw", "number_draw", "list_draw", "coin_flip", "dice_roll"}:
                    drawing.draw(db, room, token=token, actor=actor, count=message.get("count"))
                elif kind in {"update_settings", "parameter_update"}:
                    drawing.update_settings(
                        db,
                        room,
                        token=token,
                        actor=actor,
                        mode=message.get("mode"),
                        config=message.get("config", message.get("parameters")),
                        draw_policy=message.get("draw_policy"),
                    )
                elif kind == "reset":
                    drawing.reset_round(db, room, token=token, actor=actor)
                elif kind in {"invalidate", "undo"}:
                    drawing.invalidate_latest(db, room, token=token, actor=actor)
                elif kind == "end":
                    drawing.end_room(db, room, token=token, actor=actor)
                else:
                    await manager.send_error(websocket, 422, "Unknown message type")
                    continue
                await manager.broadcast_state(room_id)
            except Exception as exc:
                db.rollback()
                status = getattr(exc, "status_code", 400)
                detail = getattr(exc, "detail", "Action could not be completed")
                await manager.send_error(websocket, status, str(detail))
    except WebSocketDisconnect:
        pass
    finally:
        if manager.disconnect(room_id, client_id, websocket):
            await manager.broadcast_state(room_id)


async def cleanup_background_task() -> None:
    while True:
        try:
            await manager.cleanup_inactive_connections()
        except Exception:
            logger.exception("WebSocket cleanup failed")
        await asyncio.sleep(60)


cleanup_task: asyncio.Task | None = None
