SHELL := /bin/bash
.DEFAULT_GOAL := check
UV ?= uv

.PHONY: setup check-environment lint test check

setup:
	@for tool in bash git jq $(UV); do \
		command -v "$$tool" >/dev/null || { echo "Missing prerequisite: $$tool (see README.md)" >&2; exit 1; }; \
	done
	$(UV) sync --locked --dev

# Checks never install tools or repair the environment implicitly.
check-environment:
	@test -x .venv/bin/python || { echo "Development environment missing. Run make setup." >&2; exit 1; }
	@$(UV) sync --locked --dev --check --offline || { echo "Run make setup; dependency edits also require uv lock." >&2; exit 1; }

lint: check-environment
	$(UV) run --frozen --no-sync --offline python -m ruff check --no-fix .
	$(UV) run --frozen --no-sync --offline bash scripts/validate-hooks.sh

test: check-environment
	$(UV) run --frozen --no-sync --offline python -m pytest -q

check: lint test
