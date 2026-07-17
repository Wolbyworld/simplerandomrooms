from fastapi import FastAPI, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
from pathlib import Path
import asyncio
import logging

# Import database functions and routers
from app.models.database import create_tables
from app.routers import rooms, websocket, stats

# Create the FastAPI app
app = FastAPI(title="Random Draw Website")

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
    return templates.TemplateResponse("index.html", {"request": request})

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Disconnect endpoint for navigator.sendBeacon
@app.post("/api/disconnect")
async def handle_disconnect(
    request: Request,
    room_id: str = Query(...),
    client_id: str = Query(...)
):
    try:
        # Log the disconnect request
        logging.info(f"Received disconnect beacon from client {client_id} in room {room_id}")
        
        # Disconnect the client from the WebSocket manager
        websocket.manager.disconnect(room_id, client_id)
        
        # Return an empty response
        return Response(status_code=204)
    except Exception as e:
        logging.error(f"Error handling disconnect: {e}")
        return Response(status_code=500)

# Include routers
app.include_router(rooms.router)
app.include_router(websocket.router)
app.include_router(stats.router)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()
    
    # Start WebSocket cleanup task
    websocket.cleanup_task = asyncio.create_task(websocket.cleanup_background_task())
    
@app.on_event("shutdown")
async def shutdown_event():
    # Cancel the cleanup task if it's running
    if websocket.cleanup_task:
        websocket.cleanup_task.cancel()
        try:
            await websocket.cleanup_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 