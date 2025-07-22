.PHONY: help test lint ruff pyright format check clean reset-migrations

help: ## Show this help message
	@echo "Test project development commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Run Django tests (use ARGS="test.class.method" to specify specific tests)
	PYTHONPATH=.. uv run python manage.py test $(or $(ARGS),testdjdatalog) -v 2

reset-migrations: ## Delete and recreate migrations
	rm -rf testdjdatalog/migrations/
	mkdir -p testdjdatalog/migrations/
	touch testdjdatalog/migrations/__init__.py
	PYTHONPATH=.. uv run python manage.py makemigrations testdjdatalog
	@echo "✅ Migrations reset and recreated"

lint: ## Run linting tools (ruff, basedpyright)
	uv run --project .. ruff check testdjdatalog/ --exclude testdjdatalog/migrations/
	uv run --project .. basedpyright testdjdatalog/
	@echo "✅ Linting passed"

ruff: ## Run ruff linter only
	uv run --project .. ruff check testdjdatalog/ --exclude testdjdatalog/migrations/

pyright: ## Run basedpyright type checker
	uv run --project .. basedpyright testdjdatalog/

format: ## Auto-format code with ruff (includes import sorting)
	uv run --project .. ruff check --fix --unsafe-fixes testdjdatalog/ --exclude testdjdatalog/migrations/
	uv run --project .. ruff format testdjdatalog/ --exclude testdjdatalog/migrations/
	@echo "✅ Code formatted with import sorting"

check: format lint test ## Format, lint, and test

clean: ## Clean test artifacts
	rm -rf testdjdatalog/__pycache__/
	rm -rf testdjdatalog/migrations/__pycache__/
	rm -f db.sqlite3
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete