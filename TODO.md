To-Do Checklist
1. Project Initialization & Basic Setup
 Initialize Git repository

Run git init.

Create .gitignore (include typical Python ignores like __pycache__, venv, etc.).

 Set up Python virtual environment

python -m venv venv and activate it.

 Install dependencies

FastAPI, Uvicorn, pytest (pip install fastapi uvicorn pytest).

 Create project structure

Folders: app/, tests/, templates/.

Basic app/main.py.

 Root endpoint

/ returns "Hello, World!".

 Write unit test

Confirm endpoint returns correct response.

2. Landing Page
 Design retro-vintage HTML/CSS

templates/index.html with a simple style and large "Create Room" button.

 Serve HTML

Update / endpoint to serve index.html.

 Page load test

Verify the page responds with status 200.

Confirm the presence of the "Create Room" button in test assertions.

3. Room Creation Endpoint
 Implement /create-room (POST)

Generates UUID-based room_id.

Stores room data in an in-memory structure.

Redirects to /room/{room_id}.

 Write tests

Check unique URL generation (mock or verify generated UUID).

Confirm redirection to the room’s URL.

4. Room Page & Parameter Management
 Room HTML (templates/room.html)

Form inputs:

Coin flip toggle.

Number draw (min, max, replacement yes/no).

"Start/Draw" button or similar CTA.

 Backend endpoints

Handle form data for coin flip or number draw.

Validate parameters (e.g., min < max).

 Integration tests

Confirm form submission updates parameters.

Check error handling for invalid inputs.

5. WebSocket Real-Time Synchronization
 Implement /ws/room/{room_id}

Create a WebSocket endpoint for real-time events.

Maintain a list of connected participants.

 Broadcast events

Join/leave notifications.

Name updates.

Random action results.

 Multi-client test

Simulate two+ clients joining a room.

Confirm WebSocket messages are received by all.

6. Participant Display & Copy URL Functionality
 Update UI

Display connected users (e.g., name badges).

Update count in real-time via WebSocket.

 Implement "Copy URL" button

Use browser Clipboard API.

 Manual tests

Ensure name updates and user counts show as expected.

Verify the URL copies to clipboard.

7. Historical Log
 Add scrollable log area

In templates/room.html to list past actions.

 Backend log endpoint

Return paginated data (e.g., /room/{room_id}/logs).

 Infinite scroll

JavaScript to fetch next page as user scrolls.

 Test log retrieval

Verify logs are appended in order.

Confirm pagination works (possibly mock a large dataset).

8. Animation Implementation
 Coin flip CSS/JS

Spinning/flipping effect when a coin flip action is triggered.

 Number draw CSS/JS

Subtle reveal effect for drawn numbers.

 Manual visual tests

Check transitions/animations on coin flip or number draw.

9. Database Integration & Persistence
 Set up PostgreSQL

Install locally, confirm psql working, etc.

 SQLAlchemy ORM

Create models (e.g., Room, Log).

 CRUD endpoints

Move in-memory storage to DB-based storing and retrieving.

 Write DB tests

Test create/read/update/delete for rooms/logs.

10. Error Handling, Final Integration & Testing
 Global error handlers

Use FastAPI to return user-friendly messages.

 Endpoint-level checks

Validate inputs and handle misconfigurations gracefully.

 Full integration tests

Ensure the entire flow (from creating a room to random draws to logging) works.

Cover edge cases (invalid room, missing params, etc.).

11. Deployment to Heroku
 Heroku app creation

heroku create your-app-name.

 Provision Heroku Postgres

heroku addons:create heroku-postgresql:hobby-dev.

 Deployment

git push heroku main.

Run migrations if needed (heroku run "alembic upgrade head").

 Verification

Open site (heroku open).

Confirm all functionality (WebSocket, DB, animations) works in production.