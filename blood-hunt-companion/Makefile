.PHONY: help install api-install dev api test lint extract migrate migrate-revision clean

help:
	@echo "Blood Hunt Companion — common targets"
	@echo "  make install     install python deps (api) into a local venv at .venv/"
	@echo "  make api         run FastAPI dev server (uvicorn, port 8000)"
	@echo "  make test        run pytest"
	@echo "  make lint        run ruff + mypy"
	@echo "  make extract     translate FModel raw exports → canonical JSON"
	@echo "  make migrate     run all pending Alembic migrations against data/personal.db"
	@echo "  make migrate-revision m=\"...\"  generate a new Alembic revision"
	@echo "  make clean       remove build/test caches"

VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	$(PIP) install -e "apps/api[dev]"

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000 --app-dir apps/api

test:
	$(PY) -m pytest apps/api/tests

lint:
	$(VENV)/bin/ruff check apps/api tools
	$(VENV)/bin/mypy apps/api/app

extract:
	@echo "Reading FModel exports from data/game/_raw/, writing canonical JSON to data/game/"
	$(PY) tools/translate_game_data.py

migrate:
	cd apps/api && ../../$(PY) -m alembic upgrade head

migrate-revision:
	@if [ -z "$(m)" ]; then echo "Usage: make migrate-revision m=\"message\""; exit 1; fi
	cd apps/api && ../../$(PY) -m alembic revision --autogenerate -m "$(m)"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
