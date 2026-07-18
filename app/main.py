from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

# Import database functions and routers
from app.models.database import create_tables
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

# Include routers
app.include_router(rooms.router)
app.include_router(websocket.router)
app.include_router(stats.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
