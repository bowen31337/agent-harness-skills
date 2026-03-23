# =============================================================================
# Makefile — harness-skills project tasks
#
# Usage:
#   make lint              Run all architectural + principle checks (default)
#   make lint-json         Same, but emit a machine-parseable JSON report
#   make lint-arch         Architecture gate only (import-layer isolation)
#   make lint-principles   Principles gate only (golden-rule enforcement)
#   make lint-style        Lint gate only (ruff / style / naming)
#   make lint-fix          Run lint then auto-apply ruff fixes
#   make test              Run the full pytest suite
#   make check             lint + test in one shot (CI shortcut)
#   make fmt               Auto-format with ruff (no lint check)
#   make install           Install the package in editable mode via uv
#   make clean             Remove Python bytecode and build artefacts
# =============================================================================

SHELL     := /bin/bash
.DEFAULT_GOAL := lint

# ── tuneable variables (override from CLI: make lint PROJECT_ROOT=./src) ──────
PROJECT_ROOT  ?= .
FORMAT        ?= table
PYTEST_ARGS   ?= -v --tb=short

# ── locate the harness runner ──────────────────────────────────────────────────
# Prefer an installed 'harness' binary; fall back to 'uv run python -m ...'
ifeq ($(shell command -v harness 2>/dev/null),)
  HARNESS := uv run python -m harness_skills.cli.main
else
  HARNESS := harness
endif

# ── ruff runner (uv if available, else direct) ─────────────────────────────────
ifeq ($(shell command -v uv 2>/dev/null),)
  RUFF := ruff
else
  RUFF := uv run ruff
endif

# =============================================================================
# Lint targets — architecture, principles, and language-level checks
# =============================================================================

.PHONY: lint
## Run all three architectural gates (architecture, principles, lint) [DEFAULT]
lint:
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Harness Lint  ·  architecture · principles · lint"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	$(HARNESS) lint \
	  --format $(FORMAT) \
	  --project-root $(PROJECT_ROOT)

.PHONY: lint-json
## Emit the LintResponse as structured JSON (agent-friendly)
lint-json:
	$(HARNESS) lint \
	  --format json \
	  --project-root $(PROJECT_ROOT)

.PHONY: lint-arch
## Architecture gate only — import-layer isolation (static AST analysis)
lint-arch:
	$(HARNESS) lint \
	  --gate architecture \
	  --format $(FORMAT) \
	  --project-root $(PROJECT_ROOT)

.PHONY: lint-principles
## Principles gate only — custom golden-rule enforcement (.claude/principles.yaml)
lint-principles:
	$(HARNESS) lint \
	  --gate principles \
	  --format $(FORMAT) \
	  --project-root $(PROJECT_ROOT)

.PHONY: lint-style
## Lint gate only — ruff style, naming, and import-ordering rules
lint-style:
	$(HARNESS) lint \
	  --gate lint \
	  --format $(FORMAT) \
	  --project-root $(PROJECT_ROOT)

.PHONY: lint-fix
## Run all gates then auto-apply ruff fixes (does NOT re-run gates after fixing)
lint-fix:
	@$(MAKE) --no-print-directory lint || true
	@echo ""
	@echo "Applying ruff auto-fix …"
	$(RUFF) check $(PROJECT_ROOT) --fix --quiet
	$(RUFF) format $(PROJECT_ROOT) --quiet
	@echo "✅ ruff auto-fix applied — run 'make lint' again to confirm."

# =============================================================================
# Formatting (no-op on lint result)
# =============================================================================

.PHONY: fmt
## Auto-format all Python files with ruff (no lint check)
fmt:
	$(RUFF) format $(PROJECT_ROOT)
	$(RUFF) check  $(PROJECT_ROOT) --fix --quiet || true

# =============================================================================
# Tests
# =============================================================================

.PHONY: test
## Run the full pytest suite
test:
	uv run pytest tests/ $(PYTEST_ARGS)

.PHONY: test-browser
## Run only browser (Playwright) e2e tests
test-browser:
	uv run pytest tests/browser/ $(PYTEST_ARGS)

# =============================================================================
# Composite targets
# =============================================================================

.PHONY: check
## Full quality check: lint + tests (CI shortcut)
check: lint test

# =============================================================================
# Installation
# =============================================================================

.PHONY: install
## Install the package in editable mode (uv sync)
install:
	uv sync

# =============================================================================
# Housekeeping
# =============================================================================

.PHONY: clean
## Remove Python bytecode, egg-info, and build artefacts
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .mypy_cache/ .ruff_cache/

.PHONY: help
## Show this help message
help:
	@echo ""
	@echo "Harness-Skills Makefile targets"
	@echo "────────────────────────────────────────────────────────"
	@grep -E '^## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS="## "} /^## /{desc=$$2} /^[a-z]/{print "  " prev_target "  —  " desc} {prev_target=$$0}' || \
	  grep -E '^[a-z_-]+:|^## ' $(MAKEFILE_LIST) | \
	  sed -e '/^## /{s/^## /  /;h;d}' -e '/^[a-z]/{ s/:.*//; G; s/\n/ — /; p; d}' -d || \
	awk '/^[a-zA-Z_-]+:/{target=$$1} /^## /{gsub(/^## /,""); printf "  %-20s %s\n", target, $$0}' \
	  $(MAKEFILE_LIST)
	@echo ""
