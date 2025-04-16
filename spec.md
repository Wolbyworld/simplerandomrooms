# Simple Random Draw Website - Project Blueprint

### Preconditions
- Python installed
- Heroku CLI installed and logged in
- PostgreSQL locally available for testing

## Step-by-step Blueprint

### 1\. Project Initialization & Basic Setup

- Initialize Git repository and Python virtual environment.
- Install FastAPI, Uvicorn, pytest.
- Set up basic project structure.
- Create a simple root endpoint `/` returning "Hello, World!"
- Write and execute a unit test to confirm endpoint functionality.

### 2\. Landing Page Implementation

- Develop HTML/CSS template (`templates/index.html`) with minimalist retro-vintage design.
- Prominent "Create Room" button.
- Update root (`/`) endpoint to serve this template.
- Write tests confirming page loads correctly and button presence.

### 3\. Room Creation Endpoint

- POST endpoint `/create-room` generates UUID-based unique room URL.
- Store room data initially in an in-memory Python dictionary.
- Redirect user to `/room/{room_id}` after creation.
- Unit tests to ensure unique URL generation and redirection logic.

### 4\. Room Page & Parameter Management

- HTML template (`templates/room.html`) with forms for selecting coin flip or number draw.
- Include dynamic parameters (min/max, replacement toggle) for number draws.
- Backend endpoints for receiving and validating room parameters.
- Integration tests verifying parameter setting/updating functionality.

### 5\. WebSocket Real-Time Synchronization

- WebSocket endpoint `/ws/room/{room_id}` for real-time updates.
- Manage connected participants in each room.
- Broadcast events: join/leave, name updates, random actions.
- Tests simulating multi-client connections and verifying message broadcasts.

### 6\. Participant Display & Copy URL Functionality

- UI updates for displaying connected users ("people pills") via WebSocket.
- Implement "Copy URL" button using browser Clipboard API.
- Manual testing procedures to verify functionality.

### 7\. Historical Log Implementation

- Scrollable log area (`templates/room.html`) for past actions.
- Backend endpoint serving paginated log data.
- Infinite scrolling using JavaScript.
- Tests confirming proper log retrieval and infinite scroll operation.

### 8\. Animation Implementation

- Smooth CSS/JS animations:
  - Coin flip: spinning effect.
  - Number draw: elegant reveal.
- Integrate animations triggered by random actions.
- Manual testing instructions provided for visual checks.

### 9\. Database Integration & Persistence

- Set up PostgreSQL database with SQLAlchemy ORM.
- Database models: `Room`, `Log`.
- Migrate endpoints to database-backed storage.
- Tests covering database CRUD operations and interactions.

### 10\. Error Handling, Final Integration & Testing

- Global FastAPI error handlers with user-friendly messages.
- Endpoint-level validation/error handling.
- Integration tests covering end-to-end user workflows and error scenarios.
- Ensure all components (frontend, backend, WebSockets, database) fully integrated.

### 11\. Deployment to Heroku

- Set up Heroku app with automatic scaling.
- Configure Heroku PostgreSQL database add-on.
- Ensure local testing mirrors Heroku deployment.
- Deploy using Heroku CLI (already logged in):
```shell
heroku create your-app-name
heroku addons:create heroku-postgresql:hobby-dev
git push heroku main
heroku run "alembic upgrade head"  # If migrations are used
heroku open
```

---

**Use this detailed blueprint to guide iterative, incremental, and fully-tested development of the Simple Random Draw website.**

