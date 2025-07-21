.PHONY: help install test lint ruff pyright format check clean build publish

help: ## Show this help message
	@echo "django-datalog development commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install development dependencies
	uv sync --group dev

test: ## Run Django tests
	cd test_project && uv run python manage.py test testdjdatalog -v 2

lint: ## Run linting tools (ruff, basedpyright)
	uv run ruff check django_datalog/
	uv run basedpyright django_datalog/
	@echo "✅ Linting passed"

ruff: ## Run ruff linter only
	uv run ruff check django_datalog/

pyright: ## Run basedpyright type checker
	uv run basedpyright django_datalog/

format: ## Auto-format code with ruff (includes import sorting)
	uv run ruff check --fix --unsafe-fixes django_datalog/
	uv run ruff format django_datalog/
	@echo "✅ Code formatted with import sorting"

format-python: ## Format Python files with ruff (includes import sorting)
	uv run ruff check --fix --unsafe-fixes django_datalog/
	uv run ruff format django_datalog/
	@echo "✅ Python code formatted with import sorting"

format-test: ## Format test project code  
	uv run ruff check --fix --unsafe-fixes test_project/testdjdatalog/
	uv run ruff format test_project/testdjdatalog/
	@echo "✅ Test project formatted with import sorting"

check: format lint test ## Format, lint, and test

clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -path "./.venv" -prune -o -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -path "./.venv" -prune -o -name "*.pyc" -delete 2>/dev/null || true
	find . -path "./.venv" -prune -o -name "*.pyo" -delete 2>/dev/null || true

build: clean ## Build the package
	uv build

publish: build ## Publish to PyPI (requires authentication)
	uv publish
