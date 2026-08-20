.DEFAULT_GOAL := help

.PHONY: help install lint format-check typecheck test test-unit test-integration check run docker-build smoke

help:
	@printf '%s\n' 'Targets: install lint format-check typecheck test check run docker-build smoke'

install:
	uv sync --extra dev

lint:
	uv run ruff check app tests

format-check:
	uv run ruff format --check app tests

typecheck:
	uv run mypy app

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

check: lint format-check typecheck test

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build --tag coolproof-api:local .

smoke:
	./scripts/smoke-api.sh
