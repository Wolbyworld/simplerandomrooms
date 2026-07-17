from fastapi import Depends, FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
from pathlib import Path
import asyncio
import logging
from contextlib import asynccontextmanager

# Import database functions and routers
from sqlalchemy.orm import Session

from app.models.database import create_tables, get_db
from app.services import drawing
from app.routers import rooms, websocket, stats


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    websocket.cleanup_task = asyncio.create_task(websocket.cleanup_background_task())
    try:
        yield
    finally:
        if websocket.cleanup_task:
            websocket.cleanup_task.cancel()
            try:
                await websocket.cleanup_task
            except asyncio.CancelledError:
                pass
            websocket.cleanup_task = None

# Create the FastAPI app
app = FastAPI(title="Random Draw Website", lifespan=lifespan)

# Set up templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Define favicon endpoints
@app.get("/favicon.ico")
async def favicon():
    return FileResponse(str(BASE_DIR / "static" / "favicon.ico"))

# Define root endpoint
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Disconnect endpoint for navigator.sendBeacon
@app.post("/api/disconnect")
async def handle_disconnect(
    request: Request,
    room_id: str = Query(...),
    client_id: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        # Log the disconnect request
        logging.info(f"Received disconnect beacon from client {client_id} in room {room_id}")
        
        # Disconnect the client from the WebSocket manager
        room = drawing.find_room(db, room_id)
        disconnected = websocket.manager.disconnect(room.id, client_id)
        if disconnected:
            await websocket.manager.broadcast_state(room.id)
        
        # Return an empty response
        return Response(status_code=204)
    except Exception as e:
        logging.error(f"Error handling disconnect: {e}")
        return Response(status_code=getattr(e, "status_code", 400))

# Include routers
app.include_router(rooms.router)
app.include_router(websocket.router)
app.include_router(stats.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
