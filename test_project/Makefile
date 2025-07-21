.PHONY: help test lint ruff pyright format check clean

help: ## Show this help message
	@echo "Test project development commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Run Django tests
	uv run python manage.py test testdjdatalog -v 2

lint: ## Run linting tools (ruff, basedpyright)
	uv run --project .. ruff check testdjdatalog/
	uv run --project .. basedpyright testdjdatalog/
	@echo "✅ Linting passed"

ruff: ## Run ruff linter only
	uv run --project .. ruff check testdjdatalog/

pyright: ## Run basedpyright type checker
	uv run --project .. basedpyright testdjdatalog/

format: ## Auto-format code with ruff (includes import sorting)
	uv run --project .. ruff check --fix --unsafe-fixes testdjdatalog/
	uv run --project .. ruff format testdjdatalog/
	@echo "✅ Code formatted with import sorting"

check: format lint test ## Format, lint, and test

clean: ## Clean test artifacts
	rm -rf testdjdatalog/__pycache__/
	rm -rf testdjdatalog/migrations/__pycache__/
	rm -f db.sqlite3
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete