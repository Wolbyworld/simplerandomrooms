import os
from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient

# Set the database before importing any application module. This keeps tests
# from reading or mutating the developer/production-compatible SQLite file and
# also lets WebSocket broadcasts open independent sessions against the same DB.
_test_dir = Path(tempfile.mkdtemp(prefix="random-draw-v2-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir / 'test.sqlite'}"

from app.main import app  # noqa: E402
from app.models.database import Base, engine  # noqa: E402
from app.routers.websocket import manager  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    for mapping in (
        manager.active_rooms,
        manager.user_names,
        manager.host_tokens,
        manager.last_activity,
    ):
        mapping.clear()
    # Entering TestClient runs startup and shutdown, matching the real server.
    with TestClient(app) as test_client:
        yield test_client
