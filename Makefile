SHELL := /bin/bash
.DEFAULT_GOAL := check
UV ?= uv

.PHONY: setup check-environment lint test verify check sync-hosts check-hosts install-hosts

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
	$(UV) run --frozen --no-sync --offline python scripts/sync-hosts.py --check

sync-hosts: check-environment
	$(UV) run --frozen --no-sync --offline python scripts/sync-hosts.py

check-hosts: check-environment
	WORKFLOW_REQUIRE_PI=1 WORKFLOW_REQUIRE_AUTOLITH=1 $(UV) run --frozen --no-sync --offline python -m pytest -q tests/test_pi_host.py tests/test_autolith_host.py tests/test_host_runners.py
	$(UV) run --frozen --no-sync --offline python tests/smoke_autolith.py
	$(UV) run --frozen --no-sync --offline python tests/smoke_host_runners.py

install-hosts:
	bash scripts/install-hosts.sh

test: check-environment
	$(UV) run --frozen --no-sync --offline python -m pytest -q

verify: check-environment
	$(UV) run --frozen --no-sync --offline python tests/smoke_delivery.py

check: lint test verify
