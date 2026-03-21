#!/usr/bin/env bash
# =============================================================================
# worktree-env.sh — Generate isolated environment variables for a git worktree
#
# Usage:
#   source scripts/worktree-env.sh [WORKTREE_NAME]
#   # or to just print the env block:
#   scripts/worktree-env.sh [WORKTREE_NAME]
#
# If WORKTREE_NAME is omitted, the current directory basename is used.
#
# Port layout (slot = hash(name) % 20 + 1, range 1-20):
#   Grafana  : 3000 + slot*10   (3010 – 3200)
#   Loki     : 4000 + slot*10   (4010 – 4200)
#   Vector   : 5000 + slot*10   (5010 – 5200)
#   State svc: 8000 + slot*10   (8010 – 8200)
#   (main dev baseline keeps the original ports unchanged)
# =============================================================================

set -euo pipefail

WORKTREE_NAME="${1:-$(basename "$PWD")}"

# ── Derive a stable slot 1-20 from the worktree name ─────────────────────────
# cksum gives a CRC32 decimal; mod 20 gives 0-19, +1 gives 1-20.
_cksum=$(printf '%s' "$WORKTREE_NAME" | cksum | awk '{print $1}')
WORKTREE_SLOT=$(( (_cksum % 20) + 1 ))

# ── Compute service ports ─────────────────────────────────────────────────────
GRAFANA_PORT=$(( 3000 + WORKTREE_SLOT * 10 ))
LOKI_PORT=$(( 4000 + WORKTREE_SLOT * 10 ))
VECTOR_PORT=$(( 5000 + WORKTREE_SLOT * 10 ))
STATE_PORT=$(( 8000 + WORKTREE_SLOT * 10 ))

# ── Database path (SQLite, separate file per worktree) ────────────────────────
DB_DIR="${DB_DIR:-./.worktree-data}"
DB_PATH="${DB_DIR}/claw_forge_${WORKTREE_NAME}.db"

# ── Docker Compose project name (isolates containers) ────────────────────────
COMPOSE_PROJECT="claw_forge_wt_${WORKTREE_NAME}"

# ── Print or export ───────────────────────────────────────────────────────────
_env_block() {
  cat <<EOF
# ── Worktree isolation config for: ${WORKTREE_NAME} ──
WORKTREE_NAME=${WORKTREE_NAME}
WORKTREE_SLOT=${WORKTREE_SLOT}

# Service ports
GRAFANA_PORT=${GRAFANA_PORT}
LOKI_PORT=${LOKI_PORT}
VECTOR_PORT=${VECTOR_PORT}
STATE_PORT=${STATE_PORT}

# Database
STATE_DB_URL=sqlite+aiosqlite:///${DB_PATH}

# Docker Compose isolation
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT}
EOF
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Script executed directly → print the env block
  _env_block
  echo ""
  echo "# To apply in your shell:"
  echo "#   source <(scripts/worktree-env.sh ${WORKTREE_NAME})"
else
  # Script sourced → export variables into the calling shell
  eval "$(_env_block | grep -v '^#' | grep -v '^$')"
  export WORKTREE_NAME WORKTREE_SLOT
  export GRAFANA_PORT LOKI_PORT VECTOR_PORT STATE_PORT
  export STATE_DB_URL COMPOSE_PROJECT_NAME
  echo "[worktree-env] Slot ${WORKTREE_SLOT} → ports: Grafana=${GRAFANA_PORT} Loki=${LOKI_PORT} Vector=${VECTOR_PORT} State=${STATE_PORT}"
  echo "[worktree-env] DB: ${STATE_DB_URL}"
fi
