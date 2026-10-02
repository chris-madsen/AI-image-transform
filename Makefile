SHELL := bash
.DEFAULT_GOAL := help

.PHONY: help test cleaner-test service openspec-validate bridge-check clean

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-22s %s\n", $$1, $$2}'

test: ## Run deterministic tests
	uv run --extra dev pytest -q

cleaner-test: test ## Backwards-compatible alias for test

service: ## Run the local asynchronous image-processing service
	uv run uvicorn printify_artwork_cleaner.service:app --host $${HOST:-127.0.0.1} --port $${PORT:-8000}

bridge-check: ## Check Photopea Live adapter JavaScript syntax
	cd bridge && npm run check

openspec-validate: ## Validate the active OpenSpec change
	openspec validate rebuild-universal-image-processing-skill --type change --strict

clean: ## Remove generated local caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
