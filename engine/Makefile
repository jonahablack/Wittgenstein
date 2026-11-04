.PHONY: sync fmt lint typecheck test schemas validate-registry examples api dev-check

sync:
	uv sync --extra dev

fmt:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

test:
	uv run pytest

schemas:
	uv run python scripts/export_json_schemas.py

validate-registry:
	uv run python scripts/validate_seed_registry.py

examples:
	uv run python scripts/generate_example_data.py

api:
	uv run uvicorn wittgenstein.api.app:app --reload --host 127.0.0.1 --port 8000

dev-check: fmt lint typecheck test schemas validate-registry
