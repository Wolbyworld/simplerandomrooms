from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import random
from typing import Dict, List, Set
from datetime import datetime
import logging

from app.models.database import get_db, Room, Log

# Create router
router = APIRouter(tags=["WebSocket"])

# Active connections manager
class ConnectionManager:
    def __init__(self):
        # Map of room_id to set of connections
        self.active_rooms: Dict[str, Dict[str, WebSocket]] = {}
        # Map of room_id to dictionary of client_id: username
        self.user_names: Dict[str, Dict[str, str]] = {}
        # Track last activity time for each client
        self.last_activity: Dict[str, Dict[str, datetime]] = {}
        # Inactivity timeout in seconds (10 minutes)
        self.inactivity_timeout = 10 * 60
        
    async def connect(self, websocket: WebSocket, room_id: str, client_id: str):
        await websocket.accept()
        
        # Initialize room if it doesn't exist
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = {}
            self.user_names[room_id] = {}
            self.last_activity[room_id] = {}
        
        # Add connection to room
        self.active_rooms[room_id][client_id] = websocket
        
        # Set default username
        default_name = f"User {len(self.active_rooms[room_id])}"
        self.user_names[room_id][client_id] = default_name
        
        # Initialize last activity time
        self.last_activity[room_id][client_id] = datetime.utcnow()
        
        # Broadcast the join event
        await self.broadcast_join(room_id, client_id)
        
    def disconnect(self, room_id: str, client_id: str):
        if room_id in self.active_rooms and client_id in self.active_rooms[room_id]:
            # Remove connection
            del self.active_rooms[room_id][client_id]
            
            # Remove last activity tracking
            if room_id in self.last_activity and client_id in self.last_activity[room_id]:
                del self.last_activity[room_id][client_id]
            
            # If room is empty, remove it
            if not self.active_rooms[room_id]:
                del self.active_rooms[room_id]
                del self.user_names[room_id]
                if room_id in self.last_activity:
                    del self.last_activity[room_id]
            else:
                # Broadcast leave event
                username = self.user_names[room_id].get(client_id, "Unknown user")
                del self.user_names[room_id][client_id]
                asyncio.create_task(
                    self.broadcast_to_room(
                        room_id,
                        {
                            "type": "leave",
                            "client_id": client_id,
                            "username": username,
                            "users": self.get_users(room_id)
                        }
                    )
                )
    
    def get_users(self, room_id: str) -> List[Dict[str, str]]:
        if room_id not in self.user_names:
            return []
        
        return [
            {"client_id": client_id, "username": username}
            for client_id, username in self.user_names[room_id].items()
        ]
    
    async def broadcast_join(self, room_id: str, client_id: str):
        if room_id in self.active_rooms:
            username = self.user_names[room_id].get(client_id, "Unknown user")
            await self.broadcast_to_room(
                room_id,
                {
                    "type": "join",
                    "client_id": client_id,
                    "username": username,
                    "users": self.get_users(room_id)
                }
            )
    
    async def broadcast_to_room(self, room_id: str, message: dict):
        if room_id in self.active_rooms:
            disconnected_clients = []
            
            for client_id, connection in self.active_rooms[room_id].items():
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    disconnected_clients.append(client_id)
            
            # Clean up disconnected clients
            for client_id in disconnected_clients:
                self.disconnect(room_id, client_id)
    
    async def broadcast_random_action(self, room_id: str, client_id: str, action: dict, db: Session):
        """Broadcast a random action (coin flip or number draw) to the room"""
        if room_id in self.active_rooms:
            # Get user name
            username = self.user_names[room_id].get(client_id, "Unknown user")
            
            # Prepare message
            message = {
                "type": "random_action",
                "client_id": client_id,
                "username": username,
                "action": action["action"],
                "result": action["result"],
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Log to database
            log = Log(
                room_id=room_id,
                user_name=username,
                action=action["action"],
                result=action["result"]
            )
            db.add(log)
            db.commit()
            
            # Broadcast to room
            await self.broadcast_to_room(room_id, message)
    
    async def update_username(self, room_id: str, client_id: str, username: str):
        """Update a user's name and broadcast the change"""
        if room_id in self.user_names and client_id in self.user_names[room_id]:
            # Update name
            old_name = self.user_names[room_id][client_id]
            self.user_names[room_id][client_id] = username
            
            # Broadcast update
            await self.broadcast_to_room(
                room_id,
                {
                    "type": "name_change",
                    "client_id": client_id,
                    "old_name": old_name,
                    "new_name": username,
                    "users": self.get_users(room_id)
                }
            )
    
    async def broadcast_parameter_update(self, room_id: str, client_id: str, parameters: dict):
        """Broadcast parameter updates to all users in the room"""
        if room_id in self.active_rooms:
            # Get user name
            username = self.user_names[room_id].get(client_id, "Unknown user")
            
            # Prepare message
            message = {
                "type": "parameter_update",
                "client_id": client_id,
                "username": username,
                "parameters": parameters,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Log the parameters being sent
            logger.info(f"Broadcasting parameters to room {room_id}: {parameters}")
            
            # Track successful/failed sends
            successful_sends = 0
            failed_sends = 0
            
            # Send to each client individually to catch any errors
            for recipient_id, connection in self.active_rooms[room_id].items():
                try:
                    await connection.send_text(json.dumps(message))
                    successful_sends += 1
                except Exception as e:
                    failed_sends += 1
                    logger.error(f"Error sending parameter update to client {recipient_id}: {e}")
            
            # Log results
            logger.info(f"Parameter update broadcast complete: {successful_sends} successful, {failed_sends} failed")
            
            # If all sends failed, log a warning
            if successful_sends == 0 and failed_sends > 0:
                logger.warning(f"All parameter update broadcasts failed for room {room_id}")
            
            return successful_sends > 0
        else:
            logger.warning(f"Attempted to broadcast parameters to non-existent room {room_id}")
            return False
    
    def update_activity(self, room_id: str, client_id: str):
        """Update the last activity time for a client"""
        if room_id in self.last_activity:
            self.last_activity[room_id][client_id] = datetime.utcnow()
            
    async def cleanup_inactive_connections(self):
        """Remove connections that have been inactive for too long"""
        now = datetime.utcnow()
        cleaned_connections = 0
        
        for room_id in list(self.active_rooms.keys()):
            # Skip empty rooms
            if not self.active_rooms[room_id]:
                continue
                
            # Check each connection in the room
            for client_id in list(self.active_rooms[room_id].keys()):
                # Check last activity time
                if room_id in self.last_activity and client_id in self.last_activity[room_id]:
                    last_active = self.last_activity[room_id][client_id]
                    inactive_seconds = (now - last_active).total_seconds()
                    
                    # If inactive for too long, disconnect
                    if inactive_seconds > self.inactivity_timeout:
                        logger.info(f"Cleaning up inactive connection: client {client_id} in room {room_id} " +
                                   f"(inactive for {inactive_seconds:.1f} seconds)")
                        self.disconnect(room_id, client_id)
                        cleaned_connections += 1
        
        if cleaned_connections > 0:
            logger.info(f"Cleaned up {cleaned_connections} inactive connections")
        
        return cleaned_connections

# Create connection manager
manager = ConnectionManager()

# Import asyncio for task creation
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocket endpoint
@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: str, 
    client_id: str,
    db: Session = Depends(get_db)
):
    # Check if room exists in the database
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        logger.warning(f"Client {client_id} attempted to connect to non-existent room {room_id}")
        await websocket.close(code=1008)  # Policy violation - room doesn't exist
        return
    
    # Accept connection
    logger.info(f"Client {client_id} connecting to room {room_id}")
    await manager.connect(websocket, room_id, client_id)
    
    try:
        while True:
            # Receive JSON message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Update last activity time
            manager.update_activity(room_id, client_id)
            
            logger.debug(f"Received message from client {client_id} in room {room_id}: {message['type']}")
            
            # Handle different message types
            if message["type"] == "heartbeat":
                # Just respond with an acknowledgment
                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
                continue
            
            if message["type"] == "disconnect":
                # Explicit disconnect from client (tab closing)
                logger.info(f"Client {client_id} explicitly disconnected from room {room_id}")
                break
            
            if message["type"] == "name_change":
                await manager.update_username(room_id, client_id, message["username"])
            
            elif message["type"] == "coin_flip":
                # Perform coin flip
                result = "Heads" if random.random() < 0.5 else "Tails"
                action = {"action": "Coin Flip", "result": result}
                await manager.broadcast_random_action(room_id, client_id, action, db)
            
            elif message["type"] == "number_draw":
                # Get parameters from message or use room defaults
                min_val = message.get("min_value", room.min_value)
                max_val = message.get("max_value", room.max_value)
                with_replacement = message.get("with_replacement", room.with_replacement)
                
                # Check if parameters differ from current room settings
                params_changed = (min_val != room.min_value or 
                                 max_val != room.max_value or 
                                 with_replacement != room.with_replacement)
                
                if params_changed:
                    # Log parameter changes
                    logger.info(f"Parameters changed in room {room_id} by client {client_id}: {min_val}-{max_val} (repl: {with_replacement})")
                    
                    # Update room parameters in database
                    room.min_value = min_val
                    room.max_value = max_val
                    room.with_replacement = with_replacement
                    db.commit()
                
                # Get result and format the action
                result = str(random.randint(min_val, max_val))
                action = {"action": "Number Draw", "result": result}
                
                # Broadcast the random action to all clients
                await manager.broadcast_random_action(room_id, client_id, action, db)
                
                # If parameters changed, broadcast the update
                if params_changed:
                    logger.info(f"Broadcasting parameter update for room {room_id}")
                    await manager.broadcast_parameter_update(room_id, client_id, {
                        "min_value": min_val,
                        "max_value": max_val,
                        "with_replacement": with_replacement
                    })
    
    except WebSocketDisconnect:
        # Handle disconnection
        logger.info(f"Client {client_id} disconnected from room {room_id}")
        manager.disconnect(room_id, client_id)
    except Exception as e:
        # Handle other errors
        logger.error(f"Error in WebSocket for client {client_id} in room {room_id}: {e}")
        manager.disconnect(room_id, client_id)

# Background task for cleaning up inactive connections
async def cleanup_background_task():
    """Background task to periodically clean up inactive connections"""
    while True:
        try:
            await manager.cleanup_inactive_connections()
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
        
        # Wait for 5 minutes before next cleanup
        await asyncio.sleep(5 * 60)

# Export the background task for startup
cleanup_task = None 