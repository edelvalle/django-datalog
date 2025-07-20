.PHONY: help test test-verbose lint format install install-dev clean build publish docs

help:
	@echo "django-datalog development commands:"
	@echo ""
	@echo "  install      Install package in development mode"
	@echo "  install-dev  Install with all development dependencies"
	@echo "  test         Run tests"
	@echo "  test-verbose Run tests with verbose output"
	@echo "  lint         Run linting (ruff, mypy)"
	@echo "  format       Format code (black, isort, ruff)"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build package"
	@echo "  publish      Publish to PyPI (requires auth)"
	@echo "  docs         Build documentation"

install:
	uv pip install -e .

install-dev:
	uv pip install -e ".[dev]"

test:
	pytest

test-verbose:
	pytest -v

lint:
	ruff check djdatalog
	mypy djdatalog
	@echo "✅ Linting passed"

format:
	black djdatalog tests
	isort djdatalog tests  
	ruff check --fix djdatalog
	@echo "✅ Code formatted"

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -delete
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

build: clean
	uv build

publish: build
	uv publish

docs:
	@echo "Documentation generation not yet implemented"
	@echo "Will use mkdocs in future versions"

# Run the internal djdatalog tests
test-internal:
	cd djdatalog && python tests/run_tests.py