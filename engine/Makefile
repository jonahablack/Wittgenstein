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

# Live self-aware pipeline: build the web app, then serve app + API on http://127.0.0.1:8100.
# Optional: put ANTHROPIC_API_KEY / OPENAI_API_KEY in engine/.env (gitignored) to enable
# language-model answers; without them, answers are quoted from the document.
live:
	cd ../web && npm install --no-audit --no-fund && npm run build
	set -a; [ -f .env ] && . ./.env; set +a; uv run uvicorn wittgenstein.api.app:app --host 127.0.0.1 --port 8100

live-sample:
	uv run python scripts/fetch_sample_corpora.py
