# Developer entry points. Everything runs locally: uv for Python, npm for Node. No Docker.
PIPE = uv run --project pipeline weather-layers

.PHONY: setup pipeline pipeline-coast dev test lint typecheck format screenshots crosscheck clean-data

setup:
	uv sync --project pipeline --all-extras
	npm install
	npx playwright install chromium

pipeline:
	$(PIPE) run --area dev

pipeline-coast:
	$(PIPE) run --area coast

dev:
	npm run dev

test:
	uv run --project pipeline pytest
	npm test

lint:
	uv run --project pipeline ruff check pipeline
	uv run --project pipeline ruff format --check pipeline
	npm run lint

typecheck:
	npm run typecheck

format:
	uv run --project pipeline ruff format pipeline
	npm run format

screenshots:
	npm run screenshots

crosscheck:
	$(PIPE) crosscheck

clean-data:
	rm -rf data/out data/state
