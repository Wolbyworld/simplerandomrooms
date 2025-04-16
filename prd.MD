### Developer-Ready Project Specification: Simple Random Draw Website

#### Overview
Develop a simple, minimalist web application with retro-vintage aesthetics that allows users to create unique rooms for performing synchronized random number draws or coin flips.

#### Functional Requirements

##### Landing Page
- Minimalist design inspired by retro-vintage aesthetics (reference: Gwern.net).
- Single prominent "Create Room" button.

##### Room Creation and Management
- Clicking "Create Room" generates a persistent unique URL.
- User selects one option at room creation (permanent per room):
  - Coin flip
  - Number draw
- For number draws, parameters (min/max, with/without replacement) can be dynamically updated anytime.
- Rooms support up to 10 concurrent participants.
- Multiple tabs from the same user/browser count as individual active users.

##### User Interaction
- Shared URL access, no authentication required.
- Real-time synchronization of UI actions via WebSockets.
- Participants enter or update display names in real-time.
- Google Docs-style "people pills" display connected users at top-right.
- Draw/flip action button disabled if fewer than two users are connected, accompanied by a clear explanatory message.
- Simple "Copy URL" button for easy sharing.

##### Historical Log
- Infinite scrolling log displaying past random actions (coin flips/numbers).
- Clear and aesthetically pleasing presentation.

##### Animation
- Coin Flip: Smooth, minimalistic animation.
- Number Draw: Elegant reveal animation, simple and clean.

#### Technical Architecture

##### Frontend
- HTML/CSS/JavaScript with responsive design.
- Retro-vintage visual styling.
- WebSockets for real-time interactivity.

##### Backend
- Python backend, framework flexible (Flask/FastAPI recommended).
- WebSockets for synchronized real-time updates.
- PostgreSQL or similar database solution hosted on Heroku.
- Support for local testing environment before deploying to Heroku.

##### Data Handling
- Persistent storage of rooms until manual database clearance.
- Data tracked:
  - Rooms created
  - Random actions performed
- Entirely anonymous, no personal or authentication data stored.

#### Error Handling
- User-friendly messages for:
  - Insufficient connected participants.
  - Invalid parameter input (e.g., min greater than max).
  - Generic errors (e.g., database connection issues, WebSocket disconnects).

#### Deployment
- Hosted on Heroku with automatic scaling.
- Database persistence for rooms and internal analytics.
- Local testing capability required for easy debugging and verification before deployment.

#### Testing Plan

##### Unit Tests
- Backend API endpoints.
- Room creation logic and URL generation.
- Random number/coin flip functionality.
- WebSocket message handling.

##### Integration Tests
- End-to-end tests for user workflows:
  - Room creation
  - Real-time synchronization
  - Participant joining/leaving
  - UI updates

##### UI/UX Tests
- Responsive design verification on desktop and mobile.
- Accessibility and usability checks.

##### Load Tests
- Simulate multiple concurrent users (up to max limit).
- WebSocket performance under load.

This specification allows immediate implementation and provides comprehensive guidance for developers.