"""FastAPI ağ geçidi: sağlık kontrolü, metrikler, tarayıcı istemcisi ve sesli WebSocket."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from voice_agent import __version__
from voice_agent.gateway.engine import Engine, EngineHolder, engine_from_env
from voice_agent.gateway.sessions import MemorySessionStore, RedisSessionStore, SessionStore
from voice_agent.gateway.voice import VoiceSession
from voice_agent.telemetry.metrics import VoiceMetrics

DEFAULT_CLIENT_DIR = Path(__file__).resolve().parents[3] / "client"


def store_from_env() -> SessionStore:
    url = os.environ.get("REDIS_URL")
    return RedisSessionStore(url) if url else MemorySessionStore()


def create_app(
    engine_factory: Callable[[], Engine] = engine_from_env,
    store: SessionStore | None = None,
    metrics: VoiceMetrics | None = None,
    client_dir: Path | None = None,
    load_in_background: bool = True,
) -> FastAPI:
    holder = EngineHolder(engine_factory)
    sessions = store or store_from_env()
    voice_metrics = metrics or VoiceMetrics()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if load_in_background:
            holder.start()
        else:
            holder.load_now()
        yield

    app = FastAPI(title="voice-agent-tr", version=__version__, lifespan=lifespan)
    app.state.engine = holder
    app.state.metrics = voice_metrics

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Süreç ayakta mı (modeller yüklenmemiş olabilir)."""
        return {"status": "ok", "version": __version__}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Modeller yüklendi ve oturum deposu erişilebilir mi."""
        store_ok = await sessions.ping()
        body = {
            "engine": "ready" if holder.engine else ("error" if holder.error else "loading"),
            "store": "ok" if store_ok else "unreachable",
        }
        if holder.error:
            body["error"] = holder.error
        status = 200 if holder.engine and store_ok else 503
        return JSONResponse(body, status_code=status)

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(generate_latest(voice_metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.websocket("/ws/voice")
    async def voice(websocket: WebSocket) -> None:
        await websocket.accept()
        engine = holder.engine
        if engine is None:
            message = "Ses modelleri yükleniyor, birazdan tekrar deneyin."
            if holder.error:
                message = "Ses modelleri yüklenemedi."
            await websocket.send_json({"type": "error", "message": message})
            await websocket.close(code=1013)
            return
        session = await VoiceSession.open(
            websocket, engine, sessions, voice_metrics, websocket.query_params.get("session_id")
        )
        await session.run()

    directory = client_dir or Path(os.environ.get("CLIENT_DIR", DEFAULT_CLIENT_DIR))
    if directory.is_dir():
        app.mount("/", StaticFiles(directory=directory, html=True), name="client")
    return app


def default_app() -> FastAPI:
    """uvicorn --factory için: gerçek modeller, ortam değişkenlerinden ayarlar."""
    return create_app()
