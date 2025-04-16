from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import random
from typing import Dict, List, Set
from datetime import datetime

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
        
    async def connect(self, websocket: WebSocket, room_id: str, client_id: str):
        await websocket.accept()
        
        # Initialize room if it doesn't exist
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = {}
            self.user_names[room_id] = {}
        
        # Add connection to room
        self.active_rooms[room_id][client_id] = websocket
        
        # Set default username
        default_name = f"User {len(self.active_rooms[room_id])}"
        self.user_names[room_id][client_id] = default_name
        
        # Broadcast the join event
        await self.broadcast_join(room_id, client_id)
        
    def disconnect(self, room_id: str, client_id: str):
        if room_id in self.active_rooms and client_id in self.active_rooms[room_id]:
            # Remove connection
            del self.active_rooms[room_id][client_id]
            
            # If room is empty, remove it
            if not self.active_rooms[room_id]:
                del self.active_rooms[room_id]
                del self.user_names[room_id]
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
                "parameters": parameters
            }
            
            # Broadcast to room
            await self.broadcast_to_room(room_id, message)

# Create connection manager
manager = ConnectionManager()

# Import asyncio for task creation
import asyncio

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
        await websocket.close(code=1008)  # Policy violation - room doesn't exist
        return
    
    # Accept connection
    await manager.connect(websocket, room_id, client_id)
    
    try:
        while True:
            # Receive JSON message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
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
                    await manager.broadcast_parameter_update(room_id, client_id, {
                        "min_value": min_val,
                        "max_value": max_val,
                        "with_replacement": with_replacement
                    })
    
    except WebSocketDisconnect:
        # Handle disconnection
        manager.disconnect(room_id, client_id)
    except Exception as e:
        # Handle other errors
        print(f"Error in WebSocket: {e}")
        manager.disconnect(room_id, client_id) 