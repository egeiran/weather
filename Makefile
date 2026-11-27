# Developer entry points. Everything runs locally: uv for Python, npm for Node. No Docker.
PIPE = uv run --project pipeline weather-layers

.PHONY: setup pipeline pipeline-norway pipeline-coast dev dev-norway dev-coast test lint typecheck format screenshots crosscheck clean-data

# Large areas get their own directories so they never overwrite the dev area.
# norway = polygon around Norway and its sea (production); coast = the plain rectangle.
NORWAY_ENV = WEATHER_LAYERS_AREA=norway WEATHER_LAYERS_OUTPUT_DIR=data/norway/out WEATHER_LAYERS_STATE_DIR=data/norway/state WEATHER_LAYERS_CACHE_DIR=data/norway/cache
COAST_ENV = WEATHER_LAYERS_AREA=coast WEATHER_LAYERS_OUTPUT_DIR=data/coast/out WEATHER_LAYERS_STATE_DIR=data/coast/state WEATHER_LAYERS_CACHE_DIR=data/coast/cache

setup:
	uv sync --project pipeline --all-extras
	npm install
	npx playwright install chromium

pipeline:
	$(PIPE) run --area dev

pipeline-norway:
	$(NORWAY_ENV) $(PIPE) run

pipeline-coast:
	$(COAST_ENV) $(PIPE) run

dev:
	npm run dev

dev-norway:
	$(NORWAY_ENV) npm run dev -w web/demo -- --port 5175 --bypass-lock

dev-coast:
	$(COAST_ENV) npm run dev -w web/demo -- --port 5174 --bypass-lock

test:
	cd pipeline && uv run pytest
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
