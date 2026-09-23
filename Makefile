.PHONY: help up down logs lint test validate shell db-shell db-migrate clean-venv

COMPOSE := docker compose
API := $(COMPOSE) run --rm --no-deps ecotrack-api
DEV_INSTALL := pip install -q -e ".[dev]"

help:
	@echo "EcoTrack Backend — comandos de desenvolvimento"
	@echo ""
	@echo "  make up          Sobe API + PostgreSQL (build + detach)"
	@echo "  make down        Para e remove containers"
	@echo "  make logs        Acompanha logs da API"
	@echo "  make validate    Importa app FastAPI dentro do container"
	@echo "  make lint        Ruff check no container (Python 3.12)"
	@echo "  make test        Pytest no container"
	@echo "  make shell       Shell interativo no container da API"
	@echo "  make db-shell    psql no PostgreSQL"
	@echo "  make db-migrate  Alembic upgrade head (requer ecotrack-db)"
	@echo "  make clean-venv  Remove .venv local incorreto (ex.: Python 3.8)"
	@echo ""
	@echo "Requisito: Docker Desktop em execução (WSL2) ou 'sudo service docker start'"

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f ecotrack-api

validate:
	$(API) python -c "from app.main import app; from app.core.config import get_settings; print(app.title, get_settings().throttle_rpm)"

lint:
	$(API) sh -c "$(DEV_INSTALL) && python -m ruff check app"

test:
	$(COMPOSE) run --rm ecotrack-api sh -c "$(DEV_INSTALL) && python -m pytest -q --tb=short"

shell:
	$(API) bash

db-shell:
	$(COMPOSE) exec ecotrack-db psql -U ecotrack -d ecotrack

db-migrate:
	$(API) alembic upgrade head

clean-venv:
	rm -rf .venv
