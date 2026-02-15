.PHONY: help install format lint lint-fix typecheck test test-cov build clean dev all

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
	uv run mypy worktree_mux/ tests/

test:  ## Run tests
	uv run pytest

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=worktree_mux --cov-report=term-missing

build:  ## Build distribution packages
	uv build

clean:  ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info .mypy_cache/ .pytest_cache/ .ruff_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

dev: format lint-fix typecheck test  ## Quick dev cycle: format, lint-fix, typecheck, test

all: format lint-fix typecheck test build  ## Full pipeline: format, lint-fix, typecheck, test, build
