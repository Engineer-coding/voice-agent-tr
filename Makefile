.PHONY: install lint format typecheck test eval check up down

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

# Aşama 2'de değerlendirme altyapısı eklenecek.
eval:
	@echo "make eval: henüz senaryo yok (Aşama 2)."

check: lint typecheck test

up:
	docker compose -f deploy/docker-compose.yml up --build

down:
	docker compose -f deploy/docker-compose.yml down
