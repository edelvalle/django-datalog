# Claude Development Guide for django-datalog

This file contains important information for Claude when working on this project.

## Getting Started

When working on this project, you should always:

1. **Read README.md first** - This tells you what the project is about, its purpose, features, and usage examples
2. **Check the top of CHANGELOG.md** - This shows what recent changes have been made and what version we're on
3. **Use the Makefile** - This project uses Make for standardized commands

## Available Commands

The project has two Makefiles:

### Root Level (Main Project)
- `make test` - Run all tests using uv
- `make lint` - Run linting (ruff + basedpyright)  
- `make format` - Auto-format code with ruff
- `make check` - Run format, lint, and test in sequence
- `make build` - Build the package
- `make install` - Install in development mode
- `make publish` - Publish to PyPI
- `make clean` - Clean build artifacts

### Test Project (`test_project/`)
- `make test` - Run Django tests using uv
- `make lint` - Run linting tools
- `make format` - Auto-format test code
- `make check` - Format, lint, and test
- `make clean` - Clean test artifacts

## Testing

Always use the Makefile commands for testing:
- From root: `make test` (runs the full test suite)
- From test_project/: `make test` (runs Django-specific tests)

Do not run tests directly with python/django commands unless the Makefile doesn't work.

## Project Structure

This is a Django package that provides a datalog inference engine:
- `django_datalog/` - Main package with facts, rules, and query systems
- `test_project/` - Django test project with comprehensive test suite
- Uses uv for dependency management
- Supports Python 3.10+ and Django 5.0+

## Key Features to Remember

- **Fact-based data modeling** with Django integration
- **Logic programming** with inference rules
- **Q object constraints** for powerful filtering
- **Context-local rules** via `rule_context()` context manager
- **Performance optimized** query system

## Development Workflow

1. Read README.md and CHANGELOG.md
2. Make changes
3. Run `make format` to format code
4. Run `make lint` to check code quality
5. Run `make test` to ensure everything works
6. Update CHANGELOG.md if adding features
7. Consider updating README.md for new features

## Coding guide lines

1. Do not do imports in functions, do them at module level, except when you incur in circular imports. 
