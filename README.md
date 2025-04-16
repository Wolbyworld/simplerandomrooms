# Random Draw Website

A retro-vintage style website for random number drawing and coin flipping in real-time with friends.

## Features

- Create rooms for random draws or coin flips
- Real-time WebSocket synchronization between participants
- Historical log of actions
- Animations for coin flips and number draws
- Share room URL functionality
- Persistent storage with SQLAlchemy

## Setup

### Local Development

1. Clone the repository
   ```
   git clone <repository-url>
   cd random_number_website
   ```

2. Create and activate a virtual environment
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```
   pip install -r requirements.txt
   ```

4. Run the development server
   ```
   uvicorn app.main:app --reload
   ```

5. Open your browser to http://localhost:8000

### Running Tests

```
pytest
```

## Deployment to Heroku

1. Create a Heroku app
   ```
   heroku create your-app-name
   ```

2. Add PostgreSQL database
   ```
   heroku addons:create heroku-postgresql:hobby-dev
   ```

3. Deploy
   ```
   git push heroku main
   ```

4. Open the app
   ```
   heroku open
   ```

## Project Structure

- `app/`: Main application code
  - `main.py`: FastAPI application entry point
  - `models/`: Database models
  - `routers/`: API route handlers
  - `templates/`: HTML templates
  - `static/`: CSS, JavaScript, and other static files
- `tests/`: Test files

## License

MIT 