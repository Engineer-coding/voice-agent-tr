FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Ses bağımlılıkları (faster-whisper, Piper) varsayılan olarak kurulur; sahte CRM için gerekmez
# ama aynı imaj iki servis için de kullanılır.
ARG EXTRAS="--extra audio"

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project $EXTRAS

COPY src ./src
COPY services ./services
COPY client ./client
RUN uv sync --frozen --no-dev $EXTRAS

ENV CLIENT_DIR=/app/client
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "--no-sync", "uvicorn", "voice_agent.gateway.app:default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
