from fastapi.testclient import TestClient

from voice_agent import __version__
from voice_agent.gateway.app import create_app
from voice_agent.gateway.engine import Engine
from voice_agent.gateway.sessions import MemorySessionStore


def test_health_is_ok_while_models_load() -> None:
    """Modeller yüklenirken süreç sağlıklı sayılır ama hazır sayılmaz."""

    def never_ready() -> Engine:
        raise RuntimeError("yükleniyor")

    app = create_app(engine_factory=never_ready, store=MemorySessionStore(), client_dir=None)
    client = TestClient(app)  # lifespan çalışmaz: motor hiç yüklenmez
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
    assert client.get("/ready").json()["engine"] == "loading"
