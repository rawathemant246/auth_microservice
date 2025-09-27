SHELL := /bin/bash
POETRY ?= poetry

.DEFAULT_GOAL := help

.PHONY: help install lint format typecheck test check run migrate superuser env

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-15s %s\n", $$1, $$2}'

install: ## Install dependencies using Poetry
	$(POETRY) install --no-interaction --no-ansi

lint: ## Run static analysis with Ruff
	$(POETRY) run ruff check .

format: ## Format code with Black and auto-fix lint issues
	$(POETRY) run black .
	$(POETRY) run ruff check --fix .

typecheck: ## Run mypy static type checks
	$(POETRY) run mypy auth_microservice tests

test: ## Execute the pytest suite
	$(POETRY) run pytest -vv

check: lint typecheck test ## Run linting, type checks, and tests

run: ## Start the FastAPI application via uvicorn
	$(POETRY) run python -m auth_microservice

migrate: ## Apply database migrations
	$(POETRY) run alembic upgrade head

superuser: ## Create the platform superuser via CLI (provide USERNAME, EMAIL, FIRST, LAST, optional PASSWORD env vars)
	@if [ -z "$$USERNAME" ] || [ -z "$$EMAIL" ] || [ -z "$$FIRST" ] || [ -z "$$LAST" ]; then \
		echo "USERNAME, EMAIL, FIRST, and LAST must be set"; \
		exit 1; \
	fi
	PASS_FLAG=""; \
	if [ -n "$$PASSWORD" ]; then PASS_FLAG="--password $$PASSWORD"; fi; \
	$(POETRY) run auth-microservice createsuperuser \
		--username "$$USERNAME" \
		--email "$$EMAIL" \
		--first-name "$$FIRST" \
		--last-name "$$LAST" \
		$$PASS_FLAG

env: ## Copy the sample .env if none exists
	@if [ ! -f .env ]; then cp .env.example .env; else echo ".env already present"; fi
