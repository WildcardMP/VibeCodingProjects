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

# Cross-platform venv layout: Windows uses .venv\Scripts, POSIX uses .venv/bin
ifeq ($(OS),Windows_NT)
	VENV_BIN := $(VENV)/Scripts
	PY := $(VENV_BIN)/python.exe
	PIP := $(VENV_BIN)/pip.exe
	RUFF := $(VENV_BIN)/ruff.exe
	MYPY := $(VENV_BIN)/mypy.exe
	PYTHON_BOOTSTRAP := python
	VENV_SENTINEL := $(VENV_BIN)/python.exe
	RM_CACHES := if exist .pytest_cache rmdir /s /q .pytest_cache & if exist .mypy_cache rmdir /s /q .mypy_cache & if exist .ruff_cache rmdir /s /q .ruff_cache
	RM_PYCACHE := for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
else
	VENV_BIN := $(VENV)/bin
	PY := $(VENV_BIN)/python
	PIP := $(VENV_BIN)/pip
	RUFF := $(VENV_BIN)/ruff
	MYPY := $(VENV_BIN)/mypy
	PYTHON_BOOTSTRAP := python3
	VENV_SENTINEL := $(VENV_BIN)/activate
	RM_CACHES := rm -rf .pytest_cache .mypy_cache .ruff_cache
	RM_PYCACHE := find . -type d -name __pycache__ -exec rm -rf {} +
endif

$(VENV_SENTINEL):
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip

install: $(VENV_SENTINEL)
	$(PIP) install -e "apps/api[dev]"

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000 --app-dir apps/api

test:
	$(PY) -m pytest apps/api/tests

lint:
	$(RUFF) check apps/api tools
	$(MYPY) apps/api/app

extract:
	@echo "Reading FModel exports from data/game/_raw/, writing canonical JSON to data/game/"
	$(PY) tools/translate_game_data.py

migrate:
	cd apps/api && ../../$(PY) -m alembic upgrade head

migrate-revision:
ifeq ($(OS),Windows_NT)
	@if "$(m)"=="" (echo Usage: make migrate-revision m="message" & exit /b 1)
else
	@if [ -z "$(m)" ]; then echo "Usage: make migrate-revision m=\"message\""; exit 1; fi
endif
	cd apps/api && ../../$(PY) -m alembic revision --autogenerate -m "$(m)"

clean:
	$(RM_CACHES)
	$(RM_PYCACHE)
