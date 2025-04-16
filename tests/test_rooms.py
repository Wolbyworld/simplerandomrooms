from fastapi.testclient import TestClient
import re
from app.main import app

client = TestClient(app)

def test_create_room():
    # Test room creation (coin flip)
    response = client.post(
        "/create-room", 
        files={},  # Required for multipart/form-data
        data={"is_coin_flip": "true"},  # String value for form data
        follow_redirects=False  # Don't follow redirects
    )
    
    # Check for redirect
    assert response.status_code == 303
    
    # Extract room ID from location header
    location = response.headers["location"]
    match = re.search(r"/room/([a-f0-9-]+)", location)
    assert match is not None
    
    room_id = match.group(1)
    
    # Test that room page loads
    room_response = client.get(f"/room/{room_id}")
    assert room_response.status_code == 200
    
    # Check that page contains coin flip elements
    assert "Coin Flip" in room_response.text
    assert "flip-coin-btn" in room_response.text

def test_create_number_draw_room():
    # Test room creation (number draw)
    response = client.post(
        "/create-room", 
        files={},  # Required for multipart/form-data
        data={"is_coin_flip": "false"},  # String value for form data
        follow_redirects=False  # Don't follow redirects
    )
    
    # Check for redirect
    assert response.status_code == 303
    
    # Extract room ID from location header
    location = response.headers["location"]
    match = re.search(r"/room/([a-f0-9-]+)", location)
    assert match is not None
    
    room_id = match.group(1)
    
    # Test that room page loads
    room_response = client.get(f"/room/{room_id}")
    assert room_response.status_code == 200
    
    # Check that page contains number draw elements
    assert "Number Draw" in room_response.text
    assert "draw-number-btn" in room_response.text
    assert "min-value" in room_response.text
    assert "max-value" in room_response.text 