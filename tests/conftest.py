import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # Entering TestClient runs startup and shutdown, matching the real server.
    with TestClient(app) as test_client:
        yield test_client
