.PHONY: install lint format typecheck test eval bench-stt bench-realtime serve check chat crm up down

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

# 30 senaryo + 25 injection saldırısı; rapor eval/reports/ altına yazılır.
# Görev başarısı %85'in altındaysa veya tek bir yetkisiz araç çağrısı varsa hata döner.
eval:
	uv run python -m voice_agent.evaluation

# STT karşılaştırması ve dosya tabanlı uçtan uca hat (Hugging Face erişimi gerekir, uzun sürer).
SAMPLES ?= 100
MODELS ?= tiny base small medium large-v3-turbo
bench-stt:
	uv run --extra audio python -m voice_agent.evaluation.stt_benchmark --samples $(SAMPLES) --models $(MODELS)

# Çalışan yığına (make up) WebSocket üzerinden sentetik sesle konuşur, gecikme dökümü çıkarır.
bench-realtime:
	uv run --extra audio python -m voice_agent.evaluation.realtime_bench --prometheus http://localhost:9090

# Ağ geçidini Docker olmadan çalıştır: http://localhost:8000 (modeller ilk açılışta iner).
serve:
	uv run --extra audio uvicorn voice_agent.gateway.app:default_app --factory --port 8000

check: lint typecheck test

# Terminalden yazışarak asistanla konuş (sahte CRM süreç içinde çalışır).
chat:
	uv run python -m voice_agent.dialogue.cli

# Sahte CRM'i ayrı bir servis olarak çalıştır (http://localhost:8100).
crm:
	uv run uvicorn mock_crm.app:default_app --factory --port 8100

up:
	docker compose -f deploy/docker-compose.yml up --build

down:
	docker compose -f deploy/docker-compose.yml down
