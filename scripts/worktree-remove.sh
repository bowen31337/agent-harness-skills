#!/usr/bin/env bash
# =============================================================================
# worktree-remove.sh — WorktreeRemove hook
#
# Called by Claude Code's EnterWorktree cleanup (or manually) when a worktree
# is being removed. Stops isolated Docker services and optionally cleans up
# the database file.
#
# Environment variables provided by Claude Code:
#   WORKTREE_PATH   — absolute path to the worktree being removed
#   WORKTREE_NAME   — slug name of the worktree
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WORKTREE_PATH="${WORKTREE_PATH:-$PWD}"
WORKTREE_NAME="${WORKTREE_NAME:-$(basename "$WORKTREE_PATH")}"

echo "==> [worktree-remove] Tearing down isolation for worktree: ${WORKTREE_NAME}"

# ── 1. Load the worktree env (to know which ports/project name to stop) ───────
ENV_FILE="${WORKTREE_PATH}/.env.worktree"
if [[ -f "${ENV_FILE}" ]]; then
  set -a; source "${ENV_FILE}"; set +a
else
  # Fallback: re-derive from worktree name
  # shellcheck source=scripts/worktree-env.sh
  source "${SCRIPT_DIR}/worktree-env.sh" "${WORKTREE_NAME}"
fi

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-claw_forge_wt_${WORKTREE_NAME}}"

# ── 2. Stop & remove Docker Compose services ──────────────────────────────────
OBS_COMPOSE="${PROJECT_ROOT}/observability/docker-compose.worktree.yml"
if [[ -f "${OBS_COMPOSE}" ]] && docker compose --project-name "${COMPOSE_PROJECT_NAME}" \
      -f "${OBS_COMPOSE}" ps --quiet 2>/dev/null | grep -q .; then
  echo "    Stopping Docker services for project: ${COMPOSE_PROJECT_NAME}"
  docker compose \
    --project-name "${COMPOSE_PROJECT_NAME}" \
    -f "${OBS_COMPOSE}" \
    down --volumes --remove-orphans
  echo "    Services stopped and volumes removed."
else
  echo "    [skip] No running Docker services found for ${COMPOSE_PROJECT_NAME}"
fi

# ── 3. Optionally remove the SQLite database ─────────────────────────────────
DATA_DIR="${WORKTREE_PATH}/.worktree-data"
if [[ "${WORKTREE_CLEAN_DB:-0}" == "1" && -d "${DATA_DIR}" ]]; then
  echo "    Removing worktree database directory: ${DATA_DIR}"
  rm -rf "${DATA_DIR}"
else
  echo "    [skip] DB retained at ${DATA_DIR} (set WORKTREE_CLEAN_DB=1 to auto-remove)"
fi

# ── 4. Remove from central registry ──────────────────────────────────────────
REGISTRY="${PROJECT_ROOT}/.worktree-registry"
if [[ -f "${REGISTRY}" ]]; then
  grep -v "^${WORKTREE_NAME}=" "${REGISTRY}" > "${REGISTRY}.tmp" || true
  mv "${REGISTRY}.tmp" "${REGISTRY}"
  echo "    Removed slot from registry."
fi

echo "==> [worktree-remove] Cleanup complete for: ${WORKTREE_NAME}"
