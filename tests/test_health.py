from fastapi.testclient import TestClient

from voice_agent import __version__
from voice_agent.gateway.app import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
