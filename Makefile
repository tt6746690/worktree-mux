.PHONY: help install format lint lint-fix typecheck test test-cov build clean dev all publish release

.DEFAULT_GOAL := help

help:  ## Show this help message
	@echo "Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies with uv
	uv sync --all-extras

format:  ## Auto-format code with ruff
	uv run ruff format worktree_mux/ tests/

lint:  ## Check code with ruff
	uv run ruff check worktree_mux/ tests/

lint-fix:  ## Check and auto-fix linting issues
	uv run ruff check --fix worktree_mux/ tests/

typecheck:  ## Run mypy type checking
	uv run mypy --python-executable .venv/bin/python worktree_mux/ tests/

test:  ## Run tests
	.venv/bin/python -m pytest

test-cov:  ## Run tests with coverage report
	.venv/bin/python -m pytest --cov=worktree_mux --cov-report=term-missing

build:  ## Build distribution packages
	uv build

clean:  ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info .mypy_cache/ .pytest_cache/ .ruff_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

dev: format lint-fix typecheck test  ## Quick dev cycle: format, lint-fix, typecheck, test

all: format lint-fix typecheck test build  ## Full pipeline: format, lint-fix, typecheck, test, build

publish: build  ## Publish to PyPI (requires PYPI_API_KEY env var)
	uv publish --token $${PYPI_API_KEY}

release: all  ## Bump minor version, build, publish, and git tag
	$(eval CURRENT := $(shell grep 'version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/'))
	$(eval MAJOR := $(shell echo $(CURRENT) | cut -d. -f1))
	$(eval MINOR := $(shell echo $(CURRENT) | cut -d. -f2))
	$(eval PATCH := $(shell echo $(CURRENT) | cut -d. -f3))
	$(eval NEW_MINOR := $(shell echo $$(($(MINOR) + 1))))
	$(eval NEXT := $(MAJOR).$(NEW_MINOR).0)
	@echo "Bumping version: $(CURRENT) → $(NEXT)"
	sed -i '' 's/version = "$(CURRENT)"/version = "$(NEXT)"/' pyproject.toml
	sed -i '' 's/__version__ = "$(CURRENT)"/__version__ = "$(NEXT)"/' worktree_mux/__init__.py
	uv lock
	git add pyproject.toml uv.lock worktree_mux/__init__.py
	git commit -m "release: v$(NEXT)"
	git tag "v$(NEXT)"
	$(MAKE) clean build
	uv publish --token $${PYPI_API_KEY}
	@echo "Published v$(NEXT) to PyPI"
	@echo "Run 'git push && git push --tags' to push the release"
