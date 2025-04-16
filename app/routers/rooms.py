from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import uuid
from pathlib import Path

from app.models.database import get_db, Room, Log

# Create router
router = APIRouter(tags=["Rooms"])

# Set up templates
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Create room endpoint
@router.post("/create-room", response_class=RedirectResponse, status_code=303)
async def create_room(
    is_coin_flip: bool = Form(False), 
    db: Session = Depends(get_db)
):
    # Generate a unique room ID
    room_id = str(uuid.uuid4())
    
    # Create a new room in the database
    room = Room(
        id=room_id,
        is_coin_flip=is_coin_flip,
    )
    
    # Add to database
    db.add(room)
    db.commit()
    db.refresh(room)
    
    # Return redirect URL
    return f"/room/{room_id}"

# Room page endpoint
@router.get("/room/{room_id}")
async def get_room(
    request: Request, 
    room_id: str, 
    db: Session = Depends(get_db)
):
    # Get room from database
    room = db.query(Room).filter(Room.id == room_id).first()
    
    # If room doesn't exist, return 404
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Return room template with room data
    return templates.TemplateResponse(
        "room.html", 
        {
            "request": request, 
            "room": room,
            "room_id": room_id
        }
    )

# Update room parameters endpoint
@router.post("/room/{room_id}/update-params")
async def update_params(
    room_id: str,
    min_value: int = Form(...),
    max_value: int = Form(...),
    with_replacement: bool = Form(False),
    db: Session = Depends(get_db)
):
    # Get room from database
    room = db.query(Room).filter(Room.id == room_id).first()
    
    # If room doesn't exist, return 404
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Validate parameters
    if min_value >= max_value:
        raise HTTPException(status_code=400, detail="Minimum value must be less than maximum value")
    
    # Update room parameters
    room.min_value = min_value
    room.max_value = max_value
    room.with_replacement = with_replacement
    
    # Save to database
    db.commit()
    db.refresh(room)
    
    # Return success
    return {"success": True}

# Get room logs endpoint
@router.get("/room/{room_id}/logs")
async def get_logs(
    room_id: str,
    page: int = 0,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    # Get room from database
    room = db.query(Room).filter(Room.id == room_id).first()
    
    # If room doesn't exist, return 404
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get logs from database, paginated
    logs = (
        db.query(Log)
        .filter(Log.room_id == room_id)
        .order_by(Log.timestamp.desc())
        .offset(page * page_size)
        .limit(page_size)
        .all()
    )
    
    # Format logs for response
    formatted_logs = [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "user_name": log.user_name,
            "action": log.action,
            "result": log.result
        }
        for log in logs
    ]
    
    # Return logs
    return {"logs": formatted_logs} 