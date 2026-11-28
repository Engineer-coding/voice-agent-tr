"""FastAPI ağ geçidi. Şimdilik yalnızca sağlık kontrolü içerir."""

from fastapi import FastAPI

from voice_agent import __version__

app = FastAPI(title="voice-agent-tr", version=__version__)


@app.get("/health")
async def health() -> dict[str, str]:
    """Servisin ayakta olduğunu bildirir."""
    return {"status": "ok", "version": __version__}
