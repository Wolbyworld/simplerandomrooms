from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db, Room, Log

# Create router
router = APIRouter(tags=["Statistics"])

@router.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get statistics about room creation and draw counts"""
    # Count rooms
    room_count = db.query(func.count(Room.id)).scalar()
    
    # Count logs (each log entry is a draw or flip)
    draw_count = db.query(func.count(Log.id)).scalar()
    
    return {
        "rooms_created": room_count,
        "draws_performed": draw_count
    } 