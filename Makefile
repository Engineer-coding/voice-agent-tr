.PHONY: install lint format typecheck test eval check chat crm up down

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
