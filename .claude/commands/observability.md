# Observability — Structured Logging Configuration

Detect the project's language and logging framework, then generate a structured logging configuration (JSON/key-value output, log levels, correlation IDs, caller info) that is ready to drop in.

---

## Instructions

### Step 1 — Detect project language and existing logging dependencies

```bash
# Language / package manager signals
ls package.json pyproject.toml go.mod Cargo.toml requirements*.txt 2>/dev/null

# Node.js — check for existing logging deps
cat package.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); deps={**d.get('dependencies',{}),**d.get('devDependencies',{})}; [print(k) for k in deps if k in ('winston','pino','bunyan','log4js','signale','tslog')]" 2>/dev/null || true

# Python — check for existing logging setup
grep -r "import logging\|structlog\|loguru\|python-json-logger\|pythonjsonlogger" --include="*.py" -l . 2>/dev/null | head -5 || true
grep -E "structlog|loguru|python-json-logger" pyproject.toml requirements*.txt 2>/dev/null || true

# Go — check for slog / zap / zerolog / logrus
grep -r "log/slog\|go.uber.org/zap\|github.com/rs/zerolog\|github.com/sirupsen/logrus" go.mod go.sum 2>/dev/null || true

# Rust — check for tracing / log / slog
grep -E "tracing|slog\s*=" Cargo.toml 2>/dev/null || true
```

Determine:
- **Language**: Python / Node.js (TypeScript or JS) / Go / Rust / other
- **Existing logger**: already installed logger crate/package (use it), or none (pick the recommended default)
- **Output format preference**: JSON (default for servers/CI) or human-readable (default for CLIs)

---

### Step 2 — Choose logging framework (if none detected)

| Language | Recommended default | Notes |
|---|---|---|
| Python | `structlog` + `python-json-logger` | stdlib `logging` compatible |
| Node.js / TypeScript | `pino` | Fastest JSON logger; `winston` if already present |
| Go | `log/slog` (stdlib, Go 1.21+) | `zap` if <Go 1.21 |
| Rust | `tracing` + `tracing-subscriber` | `log` crate for simpler crates |

Announce chosen framework to the user before proceeding.

---

### Step 3A — Python: generate structured logging configuration

**If `structlog` is preferred / not yet installed**, add dependency:

```bash
# pyproject.toml project — add via uv/pip
uv add structlog python-json-logger
```

Write `src/logging_config.py` (or `<package>/logging_config.py` — use the detected source root):

```python
# logging_config.py
# Structured logging setup — JSON output in production, coloured console in dev.
# Usage:
#   from logging_config import configure_logging, get_logger
#   configure_logging()
#   log = get_logger(__name__)
#   log.info("server_started", port=8080, env="production")

from __future__ import annotations

import logging
import logging.config
import os
import sys
from typing import Any

import structlog


def _is_development() -> bool:
    return os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower() in (
        "dev", "development", "local",
    )


def configure_logging(
    level: str | None = None,
    *,
    json_output: bool | None = None,
    add_caller_info: bool = True,
) -> None:
    """Configure root logging + structlog processors.

    Call once at application startup, before any log statements.
    """
    effective_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    use_json = json_output if json_output is not None else not _is_development()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if add_caller_info:
        shared_processors.append(structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            ]
        ))

    if use_json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(effective_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*."""
    return structlog.get_logger(name)


def bind_request_context(**kwargs: Any) -> None:
    """Bind key-value pairs to the current async/thread context (e.g. request_id)."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    """Clear per-request context variables."""
    structlog.contextvars.clear_contextvars()
```

Also write `src/logging_config_example.py` showing typical usage patterns:

```python
# logging_config_example.py  (safe to delete — reference only)
from logging_config import bind_request_context, configure_logging, get_logger

configure_logging()          # call once at startup
log = get_logger(__name__)

# Plain structured event
log.info("server_started", host="0.0.0.0", port=8080)

# Bind context for a request lifetime
bind_request_context(request_id="abc-123", user_id=42)
log.info("request_received", method="GET", path="/api/items")
log.warning("slow_query", duration_ms=450, query="SELECT ...")
```

---

### Step 3B — Node.js / TypeScript: generate pino configuration

**If pino is not installed**:

```bash
npm install pino
npm install --save-dev pino-pretty @types/pino 2>/dev/null || true
```

Write `src/logger.ts` (or `logger.js` for plain JS — adjust extension accordingly):

```typescript
// src/logger.ts
// Structured JSON logger (pino).
// Usage:
//   import { logger, childLogger } from './logger';
//   logger.info({ port: 8080 }, 'server_started');
//   const reqLog = childLogger({ requestId: req.id });
//   reqLog.warn({ durationMs: 450 }, 'slow_query');

import pino from 'pino';

const isDevelopment =
  (process.env.NODE_ENV ?? 'development') === 'development';

export const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  // JSON in production; pretty-print in development (requires pino-pretty)
  transport: isDevelopment
    ? { target: 'pino-pretty', options: { colorize: true, translateTime: 'SYS:standard' } }
    : undefined,
  base: {
    pid: process.pid,
    service: process.env.SERVICE_NAME ?? 'app',
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  serializers: {
    err: pino.stdSerializers.err,
    req: pino.stdSerializers.req,
    res: pino.stdSerializers.res,
  },
  redact: {
    // Redact sensitive fields from logs
    paths: ['req.headers.authorization', '*.password', '*.token', '*.secret'],
    censor: '[REDACTED]',
  },
});

/** Create a child logger pre-bound with context fields (e.g. requestId). */
export function childLogger(bindings: Record<string, unknown>) {
  return logger.child(bindings);
}
```

**If winston is already installed**, write `src/logger.ts` using winston instead:

```typescript
// src/logger.ts — winston structured logger
import winston from 'winston';

const isDevelopment = (process.env.NODE_ENV ?? 'development') === 'development';

export const logger = winston.createLogger({
  level: process.env.LOG_LEVEL ?? 'info',
  format: isDevelopment
    ? winston.format.combine(
        winston.format.colorize(),
        winston.format.timestamp(),
        winston.format.simple(),
      )
    : winston.format.combine(
        winston.format.timestamp(),
        winston.format.errors({ stack: true }),
        winston.format.json(),
      ),
  defaultMeta: { service: process.env.SERVICE_NAME ?? 'app' },
  transports: [new winston.transports.Console()],
});

export function childLogger(meta: Record<string, unknown>) {
  return logger.child(meta);
}
```

---

### Step 3C — Go: generate slog configuration

Detect Go version to choose slog (≥1.21) vs zap:

```bash
go version 2>/dev/null || true
grep "^go " go.mod 2>/dev/null || true
```

Write `internal/logger/logger.go` (create directory if needed):

```bash
mkdir -p internal/logger
```

```go
// internal/logger/logger.go
// Structured logger using log/slog (stdlib, Go 1.21+).
// Usage:
//   logger.Setup(logger.Config{Level: slog.LevelInfo, JSON: true})
//   slog.Info("server_started", "port", 8080)
//   ctx = logger.WithContext(ctx, "request_id", requestID)
//   logger.FromContext(ctx).Info("request_received", "method", r.Method)

package logger

import (
	"context"
	"log/slog"
	"os"
)

type contextKey struct{}

// Config controls logger initialisation.
type Config struct {
	Level  slog.Level
	JSON   bool   // true = JSONHandler, false = TextHandler (human-readable)
	Output *os.File // defaults to os.Stderr
}

// Setup initialises the default slog logger.  Call once at startup.
func Setup(cfg Config) {
	out := cfg.Output
	if out == nil {
		out = os.Stderr
	}

	opts := &slog.HandlerOptions{
		Level:     cfg.Level,
		AddSource: true,
	}

	var handler slog.Handler
	if cfg.JSON {
		handler = slog.NewJSONHandler(out, opts)
	} else {
		handler = slog.NewTextHandler(out, opts)
	}

	slog.SetDefault(slog.New(handler))
}

// WithContext returns a new context carrying the given key-value attributes.
func WithContext(ctx context.Context, args ...any) context.Context {
	return context.WithValue(ctx, contextKey{}, FromContext(ctx).With(args...))
}

// FromContext retrieves the logger stored in ctx, or the default logger.
func FromContext(ctx context.Context) *slog.Logger {
	if l, ok := ctx.Value(contextKey{}).(*slog.Logger); ok && l != nil {
		return l
	}
	return slog.Default()
}
```

Write `internal/logger/logger_test.go`:

```go
package logger_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"testing"

	"<module>/internal/logger"
)

func TestJSONOutput(t *testing.T) {
	var buf bytes.Buffer
	logger.Setup(logger.Config{Level: slog.LevelDebug, JSON: true, Output: os.NewFile(0, "")})
	// verify no panic
	slog.Info("test_event", "key", "value")
	_ = buf // output goes to stderr in tests; just verify no crash
}

func TestContextPropagation(t *testing.T) {
	logger.Setup(logger.Config{Level: slog.LevelDebug, JSON: true})
	ctx := logger.WithContext(context.Background(), "request_id", "abc-123")
	l := logger.FromContext(ctx)
	if l == nil {
		t.Fatal("expected logger in context")
	}
}

func TestJSONFields(t *testing.T) {
	var buf bytes.Buffer
	h := slog.NewJSONHandler(&buf, nil)
	l := slog.New(h)
	l.Info("ping", "status", 200)
	var m map[string]any
	if err := json.Unmarshal(buf.Bytes(), &m); err != nil {
		t.Fatalf("invalid JSON: %v\noutput: %s", err, buf.String())
	}
	if m["msg"] != "ping" {
		t.Errorf("expected msg=ping, got %v", m["msg"])
	}
}
```

Replace `<module>` with the actual module path from `go.mod`.

---

### Step 3D — Rust: generate tracing configuration

Add dependencies to `Cargo.toml` if not present:

```bash
grep -E "^tracing\s*=|^tracing-subscriber\s*=" Cargo.toml 2>/dev/null || \
  cargo add tracing tracing-subscriber --features tracing-subscriber/env-filter,tracing-subscriber/json
```

Write `src/telemetry.rs`:

```rust
// src/telemetry.rs
// Structured logging/tracing setup.
// Usage:
//   telemetry::init();              // call once in main()
//   tracing::info!(port = 8080, "server_started");
//   let span = tracing::info_span!("request", request_id = %id);
//   let _guard = span.enter();

use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

/// Initialise the global tracing subscriber.
/// Reads `RUST_LOG` for level filter (default: `info`).
/// Reads `LOG_FORMAT=json` to switch to JSON output (default: pretty in dev).
pub fn init() {
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let use_json = std::env::var("LOG_FORMAT")
        .map(|v| v.eq_ignore_ascii_case("json"))
        .unwrap_or(false);

    if use_json {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().json().with_current_span(true))
            .init();
    } else {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().pretty())
            .init();
    }
}
```

Add `mod telemetry;` and `telemetry::init();` to `src/main.rs` (or `src/lib.rs`).

---

### Step 4 — Verify generated file(s) are syntactically valid

Run the appropriate check:

```bash
# Python
python3 -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src').rglob('logging_config*.py')] ; print('Python OK')" 2>/dev/null || \
python3 -m py_compile src/logging_config.py && echo "Python OK"

# Node.js / TypeScript
npx tsc --noEmit 2>/dev/null || node --input-type=module < src/logger.js 2>/dev/null || echo "Skipping TS check — run 'npx tsc --noEmit' manually"

# Go
go build ./... 2>/dev/null && echo "Go OK" || echo "Go build failed — check module path in logger_test.go"

# Rust
cargo check 2>/dev/null && echo "Rust OK"
```

Report any errors and offer to fix them.

---

### Step 5 — Environment variable reference

Print this reference block so the user knows how to configure the logger at runtime:

```
┌─────────────────────────────────────────────────────────────────┐
│  Logging environment variables                                  │
├──────────────────┬──────────────────────────────────────────────┤
│ LOG_LEVEL        │ debug | info | warn | error  (default: info) │
│ LOG_FORMAT       │ json | text  (Rust only; default: text)       │
│ ENV / ENVIRONMENT│ development → pretty output  (Py / Node)     │
│ SERVICE_NAME     │ Injected into every log line (Node)           │
│ RUST_LOG         │ e.g. info,my_crate=debug  (Rust)             │
└──────────────────┴──────────────────────────────────────────────┘
```

---

### Step 6 — Summary

Print a concise summary:

```
✅  Structured logging configured
────────────────────────────────────────────────────────────────────
 Language   : <detected language>
 Framework  : <chosen logger>
 File(s)    : <list of files written>
 Output fmt : JSON (production) / pretty (development)
 Correlation: bind_request_context() / childLogger() / WithContext()
────────────────────────────────────────────────────────────────────
Next steps:
  1. Import / call configure_logging() (or equivalent) at startup.
  2. Set LOG_LEVEL=debug locally; LOG_LEVEL=info in production.
  3. Set ENV=production (or NODE_ENV=production) to enable JSON output.
  4. Bind a request_id / trace_id per request for log correlation.
```

If any dependency was added, remind the user to commit the updated lock file.
