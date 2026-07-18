"""HTML compatibility routes and the V2 room REST API."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Form, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictInt
import qrcode
import qrcode.image.svg
from sqlalchemy.orm import Session

from app.models.database import Log, RoomEvent, get_db
from app.services import drawing

router = APIRouter(tags=["Rooms"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRoomRequest(FlexibleModel):
    mode: str = "numbers"
    config: dict[str, Any] = Field(default_factory=dict)
    draw_policy: str = "host_only"
    host_name: str = "Host"


class SettingsRequest(FlexibleModel):
    mode: str | None = None
    config: dict[str, Any] | None = None
    draw_policy: str | None = None
    actor: str = "Host"


class DrawRequest(FlexibleModel):
    # Preserve JSON's actual type at the boundary. ``int`` would coerce true,
    # numeric strings, and integral floats before the service can reject them.
    count: StrictInt | None = None
    actor: str = "Guest"


class ActorRequest(FlexibleModel):
    actor: str = "Host"


def host_token_from_headers(
    x_host_token: str | None = Header(default=None, alias="X-Host-Token"),
    authorization: str | None = Header(default=None),
) -> str | None:
    if x_host_token:
        return x_host_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def broadcast_room(room_id: str) -> None:
    # Imported lazily to avoid a router import cycle.
    from app.routers.websocket import manager

    await manager.broadcast_state(room_id)


def share_url(request: Request, code: str) -> str:
    return str(request.url_for("get_room", room_id=code))


@router.post("/api/rooms", status_code=201)
async def api_create_room(
    request: Request,
    payload: CreateRoomRequest,
    db: Session = Depends(get_db),
):
    room, token = drawing.create_room(
        db,
        mode=payload.mode,
        config=payload.config,
        draw_policy=payload.draw_policy,
        host_name=payload.host_name,
    )
    state = drawing.serialize_state(db, room, token=token)
    state["host_token"] = token
    state["share_url"] = share_url(request, room.short_code)
    return state


@router.get("/api/rooms/lookup/{short_code}")
async def api_lookup_room(
    short_code: str,
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    # This explicit route is useful to CLI clients; GET /api/rooms/{lookup}
    # accepts either the code or the internal UUID as well.
    room = drawing.find_room(db, short_code)
    return drawing.serialize_state(db, room, token=token)


@router.get("/api/rooms/{lookup}/qr.svg", name="room_qr")
async def api_room_qr(request: Request, lookup: str, db: Session = Depends(get_db)):
    room = drawing.find_room(db, lookup)
    # A migrated V1 room receives its public code lazily. Persist it before
    # returning a QR that points at that code, otherwise the next request could
    # no longer resolve the link once this read-only session closes.
    db.commit()
    url = share_url(request, room.short_code)
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    return Response(
        output.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300", "Content-Security-Policy": "default-src 'none'"},
    )


@router.get("/api/rooms/{lookup}/export")
async def api_export_room(
    lookup: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    room = drawing.find_room(db, lookup)
    events = (
        db.query(RoomEvent)
        .filter(RoomEvent.room_id == room.id)
        .order_by(RoomEvent.event_index.asc())
        .all()
    )
    # ``find_room`` may materialize a V1 room's code/default state. Exports
    # expose that code in their filename and response, so make it durable.
    db.commit()
    if format == "csv":
        filename = f"draw-history-{room.short_code}.csv"
        return Response(
            drawing.export_history_csv(events),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return {
        "room": {"code": room.short_code, "mode": room.mode},
        "history": [drawing.serialize_event(event) for event in events],
    }

@router.get("/api/rooms/{lookup}")
async def api_get_room(
    lookup: str,
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    return drawing.serialize_state(db, room, token=token)


@router.patch("/api/rooms/{lookup}")
async def api_update_room(
    lookup: str,
    payload: SettingsRequest,
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    drawing.update_settings(
        db,
        room,
        token=token,
        mode=payload.mode,
        config=payload.config,
        draw_policy=payload.draw_policy,
        actor=payload.actor,
    )
    room = drawing.find_room(db, room.id)
    await broadcast_room(room.id)
    return drawing.serialize_state(db, room, token=token)


@router.post("/api/rooms/{lookup}/draw")
async def api_draw(
    lookup: str,
    payload: DrawRequest = Body(default_factory=DrawRequest),
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    drawing.draw(db, room, token=token, actor=payload.actor, count=payload.count)
    room = drawing.find_room(db, room.id)
    await broadcast_room(room.id)
    return drawing.serialize_state(db, room, token=token)


@router.post("/api/rooms/{lookup}/reset")
async def api_reset(
    lookup: str,
    payload: ActorRequest = Body(default_factory=ActorRequest),
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    drawing.reset_round(db, room, token=token, actor=payload.actor)
    room = drawing.find_room(db, room.id)
    await broadcast_room(room.id)
    return drawing.serialize_state(db, room, token=token)


@router.post("/api/rooms/{lookup}/invalidate")
async def api_invalidate(
    lookup: str,
    payload: ActorRequest = Body(default_factory=ActorRequest),
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    drawing.invalidate_latest(db, room, token=token, actor=payload.actor)
    room = drawing.find_room(db, room.id)
    await broadcast_room(room.id)
    return drawing.serialize_state(db, room, token=token)


@router.post("/api/rooms/{lookup}/end")
async def api_end(
    lookup: str,
    payload: ActorRequest = Body(default_factory=ActorRequest),
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, lookup)
    drawing.end_room(db, room, token=token, actor=payload.actor)
    room = drawing.find_room(db, room.id)
    await broadcast_room(room.id)
    return drawing.serialize_state(db, room, token=token)


# --- V1 compatibility -----------------------------------------------------


@router.post("/create-room", response_class=RedirectResponse, status_code=303)
async def create_room_legacy(
    is_coin_flip: bool = Form(False),
    is_list_draw: bool = Form(False),
    db: Session = Depends(get_db),
):
    mode = "coin" if is_coin_flip else ("list" if is_list_draw else "numbers")
    room, token = drawing.create_room(db, mode=mode, draw_policy="anyone")
    # Fragment data is available to the page but never sent in HTTP requests or
    # normal server access logs.
    return f"/room/{room.short_code}#host={token}"


@router.get("/room/{room_id}", name="get_room")
async def get_room(request: Request, room_id: str, db: Session = Depends(get_db)):
    room = drawing.find_room(db, room_id)
    # Persist lazily materialized V1 state before rendering its short-code URL.
    # The dependency closes (and otherwise rolls back) this session after the
    # response, which previously left the rendered public code unresolvable.
    db.commit()
    return templates.TemplateResponse(
        request,
        "room.html",
        {"room": room, "room_id": room.short_code},
    )


@router.post("/room/{room_id}/update-params")
async def update_params_legacy(
    room_id: str,
    min_value: int = Form(...),
    max_value: int = Form(...),
    with_replacement: bool = Form(False),
    db: Session = Depends(get_db),
    token: str | None = Depends(host_token_from_headers),
):
    room = drawing.find_room(db, room_id)
    drawing.update_settings(
        db,
        room,
        token=token,
        config={"min": min_value, "max": max_value, "with_replacement": with_replacement},
        actor="Host",
    )
    await broadcast_room(room.id)
    return {"success": True}


@router.get("/room/{room_id}/logs")
async def get_logs_legacy(
    room_id: str,
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    room = drawing.find_room(db, room_id)
    logs = (
        db.query(Log)
        .filter(Log.room_id == room.id)
        .order_by(Log.timestamp.desc())
        .offset(page * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "user_name": drawing.clean_actor(log.user_name),
                "action": log.action,
                "result": log.result,
            }
            for log in logs
        ]
    }
