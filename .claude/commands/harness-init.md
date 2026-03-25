# Harness Init

Generate `harness-init.sh` — a self-contained bootstrap script for teams **not** using the Claude Code IDE extension. The script installs the `claude` CLI binary, scaffolds a Python and/or TypeScript Agent SDK project, wires up a `.env`, and emits a ready-to-run `run-agent.sh` / `run-agent-ts.sh` wrapper so any terminal user can drive Claude agents programmatically.

## Instructions

### Step 1: Choose the output location

Default destination is the **project root** (where this skill is invoked from). Override with `--dir <path>` when running the skill.

```bash
OUTPUT_DIR="${HARNESS_INIT_DIR:-$(pwd)}"
OUTPUT_FILE="$OUTPUT_DIR/harness-init.sh"
echo "Output: $OUTPUT_FILE"
```

### Step 2: Check whether the script already exists

```bash
if [ -f "$OUTPUT_FILE" ]; then
  echo "harness-init.sh already exists at $OUTPUT_FILE"
  echo "Existing first line: $(head -1 "$OUTPUT_FILE")"
  echo "→ Overwriting with current version."
fi
```

### Step 3: Write harness-init.sh

Use the Write tool to create `harness-init.sh` at `$OUTPUT_FILE` with exactly the content below. Do **not** truncate or abbreviate — every line must be written verbatim.

```
#!/usr/bin/env bash
# =============================================================================
# harness-init.sh — Claude Agent SDK standalone CLI harness initializer
#
# For teams NOT using the Claude Code IDE integration.
# Sets up the claude CLI binary + SDK scaffolding so you can drive
# Claude agents programmatically from any terminal.
#
# Usage:
#   bash harness-init.sh [--lang python|typescript|auto] [--dir <project-dir>]
#
# Requirements:
#   • Node.js ≥ 18  (needed to install the claude CLI)
#   • Python ≥ 3.10 (for Python SDK path)   — optional if using TypeScript
#   • npm or npx in PATH
# =============================================================================
set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[info]${RESET}  $*"; }
success() { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[error]${RESET} $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }

# ── argument parsing ──────────────────────────────────────────────────────────
LANG_CHOICE="auto"
PROJECT_DIR="$(pwd)/claude-agent-harness"

while [[ $# -gt 0 ]]; do
  case $1 in
    --lang)       LANG_CHOICE="${2:-auto}"; shift 2 ;;
    --dir)        PROJECT_DIR="${2:-.}";    shift 2 ;;
    -h|--help)
      echo "Usage: bash harness-init.sh [--lang python|typescript|auto] [--dir <dir>]"
      exit 0 ;;
    *) error "Unknown flag: $1" ;;
  esac
done

# ── banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║       Claude Agent SDK — Standalone Harness Init          ║"
echo "║   (for teams not using the Claude Code IDE extension)     ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── detect OS ────────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Linux*)  PLATFORM=linux  ;;
  Darwin*) PLATFORM=macos  ;;
  CYGWIN*|MINGW*|MSYS*) PLATFORM=windows ;;
  *)       PLATFORM=unknown ;;
esac
info "Detected platform: ${BOLD}${PLATFORM}${RESET}"

# ── prerequisite checks ───────────────────────────────────────────────────────
header "Checking prerequisites"

check_node() {
  if ! command -v node &>/dev/null; then
    error "Node.js is required (≥ 18) to install the claude CLI.\n       Install from https://nodejs.org or via nvm/fnm."
  fi
  NODE_VER=$(node --version | sed 's/v//')
  NODE_MAJOR="${NODE_VER%%.*}"
  if [[ "$NODE_MAJOR" -lt 18 ]]; then
    error "Node.js ≥ 18 required (found $NODE_VER). Please upgrade."
  fi
  success "Node.js $NODE_VER"
}

check_npm() {
  if ! command -v npm &>/dev/null; then
    error "npm not found. Install Node.js (it includes npm)."
  fi
  success "npm $(npm --version)"
}

check_python() {
  PYTHON=""
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      PY_VER=$("$cmd" --version 2>&1 | awk '{print $2}')
      PY_MAJOR="${PY_VER%%.*}"
      PY_MINOR="${PY_VER#*.}"; PY_MINOR="${PY_MINOR%%.*}"
      if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 10 ]]; then
        PYTHON="$cmd"
        success "Python $PY_VER ($cmd)"
        return 0
      fi
    fi
  done
  return 1
}

check_node
check_npm

HAS_PYTHON=false
if check_python; then
  HAS_PYTHON=true
else
  warn "Python ≥ 3.10 not found — Python SDK path will be skipped."
fi

HAS_TYPESCRIPT=false
if command -v node &>/dev/null; then
  HAS_TYPESCRIPT=true
fi

# ── resolve SDK language ──────────────────────────────────────────────────────
if [[ "$LANG_CHOICE" == "auto" ]]; then
  if $HAS_PYTHON && $HAS_TYPESCRIPT; then
    # Prefer Python when both available — ask interactively if TTY, else default Python
    if [[ -t 0 ]]; then
      echo ""
      echo "Both Python and TypeScript/Node.js are available."
      echo "  1) Python   (claude-agent-sdk)"
      echo "  2) TypeScript (npm: @anthropic-ai/claude-agent-sdk)"
      echo "  3) Both"
      read -rp "Choose SDK language [1/2/3] (default: 1): " LANG_NUM
      case "${LANG_NUM:-1}" in
        2) LANG_CHOICE="typescript" ;;
        3) LANG_CHOICE="both" ;;
        *) LANG_CHOICE="python" ;;
      esac
    else
      LANG_CHOICE="python"
    fi
  elif $HAS_PYTHON; then
    LANG_CHOICE="python"
  elif $HAS_TYPESCRIPT; then
    LANG_CHOICE="typescript"
  else
    error "No supported SDK language found. Install Python ≥ 3.10 or Node.js ≥ 18."
  fi
fi
info "SDK language: ${BOLD}${LANG_CHOICE}${RESET}"

# ── ANTHROPIC_API_KEY ─────────────────────────────────────────────────────────
header "API key setup"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  if [[ -t 0 ]]; then
    echo -e "${YELLOW}ANTHROPIC_API_KEY is not set in the current environment.${RESET}"
    read -rsp "Paste your Anthropic API key (input hidden, leave blank to skip): " APIKEY_INPUT
    echo ""
    if [[ -n "$APIKEY_INPUT" ]]; then
      export ANTHROPIC_API_KEY="$APIKEY_INPUT"
      WRITE_DOTENV=true
    else
      warn "Skipping — remember to set ANTHROPIC_API_KEY before running agents."
      WRITE_DOTENV=false
    fi
  else
    warn "ANTHROPIC_API_KEY not set and no interactive terminal to prompt. Set it manually."
    WRITE_DOTENV=false
  fi
else
  success "ANTHROPIC_API_KEY already set in environment"
  WRITE_DOTENV=false
fi

# ── install claude CLI ────────────────────────────────────────────────────────
header "Installing claude CLI (standalone)"

install_claude_cli() {
  if command -v claude &>/dev/null; then
    CLAUDE_VER=$(claude --version 2>/dev/null | head -1 || echo "unknown")
    success "claude CLI already installed: $CLAUDE_VER"
    return 0
  fi

  info "Installing @anthropic-ai/claude-code globally via npm …"
  npm install -g @anthropic-ai/claude-code --quiet
  if command -v claude &>/dev/null; then
    success "claude CLI installed: $(claude --version 2>/dev/null | head -1)"
  else
    error "claude CLI installation failed. Ensure npm global bin is in your PATH:\n  export PATH=\"\$(npm root -g)/../bin:\$PATH\""
  fi
}

install_claude_cli

# ── create project directory ──────────────────────────────────────────────────
header "Creating project at ${PROJECT_DIR}"

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
success "Working in $(pwd)"

# ── write .env ────────────────────────────────────────────────────────────────
if [[ "${WRITE_DOTENV:-false}" == "true" && -n "${ANTHROPIC_API_KEY:-}" ]]; then
  if [[ ! -f .env ]]; then
    printf 'ANTHROPIC_API_KEY=%s\n' "$ANTHROPIC_API_KEY" > .env
    success "Wrote .env"
  else
    warn ".env already exists — not overwritten"
  fi
  # add to .gitignore
  if [[ ! -f .gitignore ]] || ! grep -q "^\.env$" .gitignore 2>/dev/null; then
    echo ".env" >> .gitignore
    echo "*.env" >> .gitignore
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# PYTHON SCAFFOLD
# ─────────────────────────────────────────────────────────────────────────────
scaffold_python() {
  header "Python scaffold"

  # ── virtual env ──────────────────────────────────────────────────────────
  if [[ ! -d .venv ]]; then
    info "Creating virtual environment …"
    "$PYTHON" -m venv .venv
    success ".venv created"
  else
    success ".venv already exists"
  fi

  PIP=".venv/bin/pip"
  PYTHON_VENV=".venv/bin/python"

  info "Installing claude-agent-sdk …"
  "$PIP" install --quiet --upgrade pip
  "$PIP" install --quiet "claude-agent-sdk"
  success "claude-agent-sdk installed"

  # ── src/agent.py ──────────────────────────────────────────────────────────
  mkdir -p src
  if [[ ! -f src/agent.py ]]; then
    cat > src/agent.py <<'AGENT_PY'
"""
agent.py — Standalone Claude Agent SDK harness entry point.

Usage:
  python src/agent.py "Explain what this repo does"
  python src/agent.py --tools Read,Glob,Grep "Find all TODO comments"
  python src/agent.py --help
"""

import argparse
import asyncio
import os
import sys

import anyio
from claude_agent_sdk import (
    ClaudeAgentOptions,
    CLIConnectionError,
    CLINotFoundError,
    ResultMessage,
    SystemMessage,
    query,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run a Claude agent query from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/agent.py "Summarise this codebase"
  python src/agent.py --tools Read,Glob,Grep "Find every TODO"
  python src/agent.py --cwd /path/to/project --max-turns 10 "Refactor utils.py"
  python src/agent.py --model claude-opus-4-6 "Solve this hard problem"
        """,
    )
    p.add_argument("prompt", help="Natural-language prompt for the agent")
    p.add_argument(
        "--tools",
        default="Read,Glob,Grep",
        help="Comma-separated list of allowed tools (default: Read,Glob,Grep)",
    )
    p.add_argument(
        "--cwd",
        default=None,
        help="Working directory for file operations (default: current dir)",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Maximum agent turns before stopping (default: 30)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Model ID to use (default: determined by CLI)",
    )
    p.add_argument(
        "--permission-mode",
        choices=["default", "plan", "acceptEdits", "dontAsk"],
        default="default",
        help="How to handle permission prompts (default: default)",
    )
    p.add_argument(
        "--system-prompt",
        default=None,
        help="Custom system prompt",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print all message types, not just the final result",
    )
    return p


async def run(args: argparse.Namespace) -> int:
    allowed_tools = [t.strip() for t in args.tools.split(",") if t.strip()]

    options_kwargs = dict(
        allowed_tools=allowed_tools,
        max_turns=args.max_turns,
        permission_mode=args.permission_mode,
    )
    if args.cwd:
        options_kwargs["cwd"] = os.path.abspath(args.cwd)
    if args.model:
        options_kwargs["model"] = args.model
    if args.system_prompt:
        options_kwargs["system_prompt"] = args.system_prompt

    options = ClaudeAgentOptions(**options_kwargs)

    exit_code = 0
    try:
        async for message in query(prompt=args.prompt, options=options):
            if isinstance(message, ResultMessage):
                if args.verbose:
                    print(f"\n[result]\n{message.result}", flush=True)
                else:
                    print(message.result, flush=True)
            elif isinstance(message, SystemMessage):
                if args.verbose:
                    print(f"[system:{message.subtype}] session={message.session_id}", flush=True)
            elif args.verbose:
                print(f"[{type(message).__name__}] {message}", flush=True)
    except CLINotFoundError:
        print(
            "ERROR: claude CLI not found.\n"
            "  Install with:  npm install -g @anthropic-ai/claude-code\n"
            "  Then ensure it is in your PATH.",
            file=sys.stderr,
        )
        exit_code = 1
    except CLIConnectionError as exc:
        print(f"ERROR: Could not connect to claude CLI: {exc}", file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        exit_code = 130

    return exit_code


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load .env if python-dotenv available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "WARNING: ANTHROPIC_API_KEY is not set. "
            "Export it or add it to a .env file.",
            file=sys.stderr,
        )

    sys.exit(anyio.run(run, args))


if __name__ == "__main__":
    main()
AGENT_PY
    success "src/agent.py written"
  fi

  # ── run-agent shell wrapper ───────────────────────────────────────────────
  if [[ ! -f run-agent.sh ]]; then
    cat > run-agent.sh <<'RUN_AGENT'
#!/usr/bin/env bash
# run-agent.sh — wrapper that activates the venv and runs src/agent.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f .env ]]; then
  set -o allexport
  source .env
  set +o allexport
fi

# Activate venv
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
else
  echo "ERROR: .venv not found. Run harness-init.sh first." >&2
  exit 1
fi

exec python src/agent.py "$@"
RUN_AGENT
    chmod +x run-agent.sh
    success "run-agent.sh written & made executable"
  fi

  # ── README snippet ────────────────────────────────────────────────────────
  if [[ ! -f README.md ]]; then
    cat > README.md <<'README'
# Claude Agent Harness (Python)

Standalone CLI harness for the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).
No Claude Code IDE extension required.

## Quick start

\`\`\`bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Set your API key (or add to .env)
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Run a query
./run-agent.sh "Explain what this repository does"

# Or directly:
python src/agent.py --tools Read,Glob,Grep "Find all TODO comments"
\`\`\`

## Options

\`\`\`
usage: agent.py [-h] [--tools TOOLS] [--cwd CWD] [--max-turns N]
                [--model MODEL] [--permission-mode MODE]
                [--system-prompt TEXT] [--verbose]
                prompt

positional arguments:
  prompt                Natural-language prompt for the agent

options:
  --tools               Comma-separated allowed tools (default: Read,Glob,Grep)
  --cwd                 Working directory for file operations
  --max-turns N         Max agent turns (default: 30)
  --model MODEL         Model ID (default: determined by CLI)
  --permission-mode     default | plan | acceptEdits | dontAsk
  --system-prompt TEXT  Custom system prompt
  --verbose / -v        Print all message types
\`\`\`

## Available tools

| Tool      | Description                    |
|-----------|--------------------------------|
| Read      | Read files                     |
| Write     | Create new files               |
| Edit      | Make precise file edits        |
| Bash      | Execute shell commands         |
| Glob      | Find files by pattern          |
| Grep      | Search file contents           |
| WebSearch | Search the web                 |
| WebFetch  | Fetch and analyse web pages    |
| Agent     | Spawn subagents                |

## Extending

Edit `src/agent.py` to add custom system prompts, hooks, MCP servers, or
structured output schemas. See the [Python Agent SDK docs](https://github.com/anthropics/claude-agent-sdk-python).
README
    success "README.md written"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# TYPESCRIPT SCAFFOLD
# ─────────────────────────────────────────────────────────────────────────────
scaffold_typescript() {
  header "TypeScript scaffold"

  mkdir -p ts-harness/src

  # ── package.json ──────────────────────────────────────────────────────────
  if [[ ! -f ts-harness/package.json ]]; then
    cat > ts-harness/package.json <<'PKGJSON'
{
  "name": "claude-agent-harness",
  "version": "1.0.0",
  "description": "Standalone Claude Agent SDK CLI harness",
  "private": true,
  "type": "module",
  "scripts": {
    "agent": "npx tsx src/agent.ts",
    "build": "npx tsc"
  },
  "dependencies": {
    "@anthropic-ai/claude-agent-sdk": "latest"
  },
  "devDependencies": {
    "tsx": "latest",
    "typescript": "latest",
    "@types/node": "latest"
  }
}
PKGJSON
    success "ts-harness/package.json written"
  fi

  # ── tsconfig.json ─────────────────────────────────────────────────────────
  if [[ ! -f ts-harness/tsconfig.json ]]; then
    cat > ts-harness/tsconfig.json <<'TSCONFIG'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "outDir": "dist",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*"]
}
TSCONFIG
    success "ts-harness/tsconfig.json written"
  fi

  # ── src/agent.ts ──────────────────────────────────────────────────────────
  if [[ ! -f ts-harness/src/agent.ts ]]; then
    cat > ts-harness/src/agent.ts <<'AGENT_TS'
/**
 * agent.ts — Standalone Claude Agent SDK harness entry point (TypeScript).
 *
 * Usage:
 *   npx tsx src/agent.ts "Explain what this repo does"
 *   npx tsx src/agent.ts --tools Read,Glob,Grep "Find all TODO comments"
 *   npx tsx src/agent.ts --help
 */

import { query } from "@anthropic-ai/claude-agent-sdk";
import path from "path";

// ── Minimal arg parser (no extra deps) ────────────────────────────────────
interface CliArgs {
  prompt: string;
  tools: string[];
  cwd?: string;
  maxTurns: number;
  model?: string;
  permissionMode: "default" | "plan" | "acceptEdits" | "dontAsk";
  systemPrompt?: string;
  verbose: boolean;
}

function printHelp(): void {
  console.log(`
Usage: npx tsx src/agent.ts [options] <prompt>

Options:
  --tools <list>         Comma-separated allowed tools (default: Read,Glob,Grep)
  --cwd <path>           Working directory for file operations
  --max-turns <n>        Max agent turns before stopping (default: 30)
  --model <id>           Model ID (default: determined by CLI)
  --permission-mode <m>  default | plan | acceptEdits | dontAsk
  --system-prompt <text> Custom system prompt
  --verbose / -v         Print all message types
  --help / -h            Show this help message

Examples:
  npx tsx src/agent.ts "Summarise this codebase"
  npx tsx src/agent.ts --tools Read,Glob,Grep "Find every TODO"
  npx tsx src/agent.ts --cwd /path/to/project "Refactor utils.ts"
`);
}

function parseArgs(argv: string[]): CliArgs {
  const args = argv.slice(2); // strip node + script
  const result: Partial<CliArgs> & { tools?: string } = {
    maxTurns: 30,
    permissionMode: "default",
    verbose: false,
  };
  const positional: string[] = [];

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    switch (a) {
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
        break;
      case "--tools":
        result.tools = args[++i];
        break;
      case "--cwd":
        result.cwd = path.resolve(args[++i]);
        break;
      case "--max-turns":
        result.maxTurns = parseInt(args[++i], 10);
        break;
      case "--model":
        result.model = args[++i];
        break;
      case "--permission-mode":
        result.permissionMode = args[++i] as CliArgs["permissionMode"];
        break;
      case "--system-prompt":
        result.systemPrompt = args[++i];
        break;
      case "--verbose":
      case "-v":
        result.verbose = true;
        break;
      default:
        positional.push(a);
    }
  }

  const prompt = positional.join(" ").trim();
  if (!prompt) {
    printHelp();
    process.exit(1);
  }

  return {
    prompt,
    tools: (result.tools ?? "Read,Glob,Grep")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    cwd: result.cwd,
    maxTurns: result.maxTurns ?? 30,
    model: result.model,
    permissionMode: result.permissionMode ?? "default",
    systemPrompt: result.systemPrompt,
    verbose: result.verbose ?? false,
  };
}

// ── Main ───────────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn(
      "WARNING: ANTHROPIC_API_KEY is not set. Export it or add it to a .env file."
    );
  }

  const args = parseArgs(process.argv);

  const options: Parameters<typeof query>[0]["options"] = {
    allowedTools: args.tools,
    maxTurns: args.maxTurns,
    permissionMode: args.permissionMode,
    ...(args.cwd && { cwd: args.cwd }),
    ...(args.model && { model: args.model }),
    ...(args.systemPrompt && { systemPrompt: args.systemPrompt }),
  };

  try {
    for await (const message of query({ prompt: args.prompt, options })) {
      if ("result" in message) {
        // ResultMessage
        if (args.verbose) {
          console.log(`\n[result]\n${message.result}`);
        } else {
          console.log(message.result);
        }
      } else if (args.verbose) {
        console.log(`[${message.type}]`, JSON.stringify(message).slice(0, 200));
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("CLI not found") || msg.includes("ENOENT")) {
      console.error(
        "ERROR: claude CLI not found.\n" +
          "  Install with:  npm install -g @anthropic-ai/claude-code\n" +
          "  Then ensure it is in your PATH."
      );
      process.exit(1);
    }
    throw err;
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
AGENT_TS
    success "ts-harness/src/agent.ts written"
  fi

  # ── install npm deps ──────────────────────────────────────────────────────
  (
    cd ts-harness
    info "Running npm install in ts-harness/ …"
    npm install --quiet --no-fund --no-audit
    success "npm packages installed"
  )

  # ── run-agent-ts.sh wrapper ───────────────────────────────────────────────
  if [[ ! -f run-agent-ts.sh ]]; then
    cat > run-agent-ts.sh <<'RUN_AGENT_TS'
#!/usr/bin/env bash
# run-agent-ts.sh — wrapper that runs the TypeScript harness
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f .env ]]; then
  set -o allexport
  source .env
  set +o allexport
fi

exec node ts-harness/node_modules/.bin/tsx ts-harness/src/agent.ts "$@"
RUN_AGENT_TS
    chmod +x run-agent-ts.sh
    success "run-agent-ts.sh written & made executable"
  fi
}

# ── run scaffold(s) ───────────────────────────────────────────────────────────
case "$LANG_CHOICE" in
  python)
    if ! $HAS_PYTHON; then error "Python ≥ 3.10 required for Python scaffold."; fi
    scaffold_python
    ;;
  typescript)
    scaffold_typescript
    ;;
  both)
    $HAS_PYTHON && scaffold_python || warn "Skipping Python scaffold (no Python ≥ 3.10 found)"
    scaffold_typescript
    ;;
  *)
    error "Unknown lang choice: $LANG_CHOICE"
    ;;
esac

# ── .gitignore ────────────────────────────────────────────────────────────────
{
  for entry in ".venv" "ts-harness/node_modules" "ts-harness/dist" \
               "__pycache__" "*.pyc" ".env" "*.env"; do
    if ! grep -qxF "$entry" .gitignore 2>/dev/null; then
      echo "$entry" >> .gitignore
    fi
  done
}
success ".gitignore updated"

# ── final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  Harness initialised at: ${PROJECT_DIR}${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════${RESET}"
echo ""

if [[ "$LANG_CHOICE" == "python" || "$LANG_CHOICE" == "both" ]] && $HAS_PYTHON; then
  echo -e "${BOLD}Python — quick start:${RESET}"
  echo "  cd ${PROJECT_DIR}"
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  echo '  ./run-agent.sh "Explain what this repo does"'
  echo '  # or:'
  echo '  source .venv/bin/activate'
  echo '  python src/agent.py --tools Read,Glob,Grep "Find all TODO comments"'
  echo ""
fi

if [[ "$LANG_CHOICE" == "typescript" || "$LANG_CHOICE" == "both" ]]; then
  echo -e "${BOLD}TypeScript — quick start:${RESET}"
  echo "  cd ${PROJECT_DIR}"
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  echo '  ./run-agent-ts.sh "Explain what this repo does"'
  echo '  # or:'
  echo '  cd ts-harness && npx tsx src/agent.ts "Find all TODO comments"'
  echo ""
fi

echo -e "${CYAN}Docs:${RESET}  https://github.com/anthropics/claude-agent-sdk-python"
echo -e "${CYAN}      ${RESET}  https://github.com/anthropics/claude-agent-sdk-typescript"
echo ""
```

### Step 4: Make it executable

```bash
chmod +x "$OUTPUT_FILE"
echo "Made executable: $OUTPUT_FILE"
```

### Step 5: Verify

```bash
bash "$OUTPUT_FILE" --help
```

Expected output: `Usage: bash harness-init.sh [--lang python|typescript|auto] [--dir <dir>]`

### Step 6: Confirm and print delivery card

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  harness-init.sh — generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  File     : <OUTPUT_FILE>
  Mode     : executable (chmod +x)
  Size     : <line count> lines

  What it does
  ├─ Checks prerequisites  : Node.js ≥ 18, npm, Python ≥ 3.10
  ├─ Installs claude CLI   : npm install -g @anthropic-ai/claude-code
  ├─ Prompts for API key   : writes ANTHROPIC_API_KEY to .env (interactive)
  ├─ Python scaffold       : .venv + claude-agent-sdk + src/agent.py + run-agent.sh
  └─ TypeScript scaffold   : ts-harness/ + @anthropic-ai/claude-agent-sdk + run-agent-ts.sh

  Share with your team
  ├─ Commit harness-init.sh to your repo, or
  └─ curl -fsSL <raw-url> | bash -s -- --lang python --dir ./my-harness

  Quick run (from any terminal, no Claude Code needed)
    bash harness-init.sh                         # auto-detect language
    bash harness-init.sh --lang python           # Python only
    bash harness-init.sh --lang typescript       # TypeScript only
    bash harness-init.sh --lang both --dir ./ai  # both, custom dir

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Notes

- The script is **idempotent** — re-running it on an existing directory is safe; it skips files that already exist.
- It works in **non-interactive** (CI) mode: when stdin is not a TTY it skips all prompts and defaults to Python + no `.env` write.
- The generated `src/agent.py` and `ts-harness/src/agent.ts` are **full-featured starting points** — teams extend them with custom system prompts, MCP servers, hooks, or structured output schemas.
- No Claude Code, no IDE extension, no `claw-forge` toolchain required — the only hard dependency is `npm` (for the `claude` CLI binary).
