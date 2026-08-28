test:
	uv run pytest

lint:
	uv run ruff check src tests && uv run mypy --strict src/

.PHONY: test lint
