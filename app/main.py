from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

# Import database functions and routers
from app.models.database import create_tables
from app.routers import rooms, websocket

# Create the FastAPI app
app = FastAPI(title="Random Draw Website")

# Set up templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Define root endpoint
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Include routers
app.include_router(rooms.router)
app.include_router(websocket.router)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 