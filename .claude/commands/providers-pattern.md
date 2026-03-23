# Providers Pattern

Scan the codebase for direct imports of cross-cutting concern libraries (logging, auth,
config), generate abstract provider interfaces that domains must depend on instead, produce
concrete adapter implementations wrapping the real libraries, and write **blocking**
principles into `.claude/principles.yaml` so that `/check-code` and `/review-pr` catch
regressions automatically.

---

## Background

Cross-cutting concerns are capabilities that every domain needs but that do not belong to
any one domain.  Letting each domain import the underlying library directly creates tight
coupling — swapping `structlog` for `loguru`, rotating an auth library, or changing config
loading breaks every domain at once.

The **Providers Pattern** decouples domains from implementations:

```
Before                              After
──────────────────────────────      ──────────────────────────────
orders/service.py                   orders/service.py
  import structlog                    from providers import LoggingProvider
  import jwt                          from providers import AuthProvider
  import os                           from providers import ConfigProvider
       │                                     │
       └── coupled to library            injected at startup
                                          (swappable, mockable)
```

---

## Instructions

### Step 0: Detect language(s)

```bash
# Python?
find . -name "*.py" -not -path "./.venv/*" -not -path "./node_modules/*" | head -5

# TypeScript / JavaScript?
find . -name "*.ts" -o -name "*.tsx" -o -name "*.js" \
  | grep -v node_modules | grep -v dist | head -5
```

Set `LANG_MODE` to `python`, `js`, or `both`.

---

### Step 1: Discover domain packages

Reuse the same domain-discovery logic as `/module-boundaries`.

**Python:**

```bash
find . -name "__init__.py" \
  -not -path "./.venv/*" \
  -not -path "./node_modules/*" \
  -not -path "*/tests/*" \
  -not -path "*/test_*" \
  | sed 's|/__init__.py||' \
  | sort
```

**JS/TS:**

```bash
find src -\( -name "index.ts" -o -name "index.js" \) \
  | grep -v node_modules | grep -v dist | grep -v __tests__ \
  | sed 's|/index\.[tj]s||' \
  | sort
```

Skip the `providers/` directory itself — it is infrastructure, not a domain.

---

### Step 2: Scan for direct cross-cutting imports

For each discovered domain, grep for direct imports of the well-known concern libraries
listed below.  Do **not** read file contents beyond the import block — just collect the
import lines and their locations.

#### 2a. Logging libraries

**Python:**

```bash
grep -rn \
  -e "^import logging" \
  -e "^from logging" \
  -e "^import structlog" \
  -e "^from structlog" \
  -e "^import loguru" \
  -e "^from loguru" \
  --include="*.py" \
  --exclude-dir=".venv" \
  --exclude-dir="tests" \
  <domain>/
```

**JS/TS:**

```bash
grep -rn \
  -e "from 'winston'" \
  -e "from \"winston\"" \
  -e "from 'pino'" \
  -e "from \"pino\"" \
  -e "from 'bunyan'" \
  -e "from \"bunyan\"" \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  <domain>/
```

#### 2b. Auth / identity libraries

**Python:**

```bash
grep -rn \
  -e "^import jwt" \
  -e "^from jwt" \
  -e "^import jose" \
  -e "^from jose" \
  -e "^from passlib" \
  -e "^from authlib" \
  -e "^import bcrypt" \
  --include="*.py" \
  --exclude-dir=".venv" \
  --exclude-dir="tests" \
  <domain>/
```

**JS/TS:**

```bash
grep -rn \
  -e "from 'jsonwebtoken'" \
  -e "from \"jsonwebtoken\"" \
  -e "from 'jose'" \
  -e "from \"jose\"" \
  -e "from 'bcrypt'" \
  -e "from \"bcrypt\"" \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  <domain>/
```

#### 2c. Config / settings libraries

**Python:**

```bash
grep -rn \
  -e "^import os$" \
  -e "^from os import" \
  -e "^from pydantic_settings" \
  -e "^from dynaconf" \
  -e "^from dotenv" \
  -e "^import environ" \
  --include="*.py" \
  --exclude-dir=".venv" \
  --exclude-dir="tests" \
  <domain>/
```

**JS/TS:**

```bash
grep -rn \
  -e "process\.env\." \
  -e "from 'dotenv'" \
  -e "from \"dotenv\"" \
  -e "from 'config'" \
  -e "from \"config\"" \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  <domain>/
```

Classify every hit as `logging`, `auth`, or `config` and record:

```
{ concern, domain, file, line, import_text }
```

---

### Step 3: Build the violation report

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Providers Pattern — Direct-Import Scan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Domain                  logging   auth   config   total violations
  ──────────────────────────────────────────────────────────────────
  orders                     2        1       3           6
  payments                   0        3       1           4
  notifications              1        0       0           1
  users                      0        0       0           0  ✅

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Violation details:

  [logging]
    orders/service.py:4       import structlog
    orders/tasks.py:2         from loguru import logger
    notifications/handler.py:1  import logging

  [auth]
    orders/checkout.py:9      from jose import jwt
    payments/gateway.py:3     import jwt
    payments/refund.py:12     from passlib.context import CryptContext
    payments/webhook.py:6     from passlib.context import CryptContext

  [config]
    orders/service.py:1       import os
    orders/tasks.py:1         import os
    orders/models.py:7        from pydantic_settings import BaseSettings
    payments/gateway.py:1     import os

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 4: Generate provider interfaces

Create or update the `providers/` package at the project source root.  Only write files
that don't already exist, or show a diff preview if they do.

#### 4a. Package init

**Python — `providers/__init__.py`:**

```python
"""
providers — cross-cutting concern interfaces.

Domains import from here; they never import the underlying library directly.

    from providers import LoggingProvider, AuthProvider, ConfigProvider

Concrete implementations live in providers/impl/ and are wired up at
application startup (e.g. in app.py or conftest.py).
"""

from providers.logging import LoggingProvider
from providers.auth import AuthProvider
from providers.config import ConfigProvider

__all__ = ["LoggingProvider", "AuthProvider", "ConfigProvider"]
```

**JS/TS — `src/providers/index.ts`:**

```ts
// providers/index.ts — cross-cutting concern interfaces.
// Domains import from here; never import the underlying library directly.
export type { LoggingProvider } from './logging';
export type { AuthProvider } from './auth';
export type { ConfigProvider } from './config';
```

#### 4b. Logging provider

**Python — `providers/logging.py`:**

```python
"""Abstract logging provider — domains depend on this, not on a specific library."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LoggingProvider(Protocol):
    """Minimal structured-logging interface.

    Implementations must be provided at application startup via dependency
    injection or a service locator.  Test doubles can use a no-op or
    in-memory implementation.
    """

    def debug(self, message: str, **context: Any) -> None: ...
    def info(self, message: str, **context: Any) -> None: ...
    def warning(self, message: str, **context: Any) -> None: ...
    def error(self, message: str, **context: Any) -> None: ...
    def critical(self, message: str, **context: Any) -> None: ...
    def bind(self, **context: Any) -> "LoggingProvider": ...
```

**JS/TS — `src/providers/logging.ts`:**

```ts
/** Abstract logging provider — domains depend on this, not on a specific library. */
export interface LoggingProvider {
  debug(message: string, context?: Record<string, unknown>): void;
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, unknown>): void;
  error(message: string, context?: Record<string, unknown>): void;
  child(context: Record<string, unknown>): LoggingProvider;
}
```

#### 4c. Auth provider

**Python — `providers/auth.py`:**

```python
"""Abstract auth provider — domains depend on this, not on jwt/passlib/etc."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    """Token issuance, verification, and password hashing interface.

    A concrete implementation wraps the actual JWT / hashing library.
    Test doubles can return deterministic tokens without crypto overhead.
    """

    def create_token(self, subject: str, claims: dict[str, Any] | None = None) -> str:
        """Issue a signed token for *subject* with optional extra *claims*."""
        ...

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify *token* and return its decoded claims.

        Raises AuthenticationError on invalid or expired tokens.
        """
        ...

    def hash_password(self, plain: str) -> str:
        """Return a salted hash of *plain*."""
        ...

    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True iff *plain* matches *hashed*."""
        ...
```

**JS/TS — `src/providers/auth.ts`:**

```ts
/** Abstract auth provider — domains depend on this, not on jsonwebtoken/jose/etc. */
export interface AuthProvider {
  createToken(subject: string, claims?: Record<string, unknown>): string;
  verifyToken(token: string): Record<string, unknown>;
  hashPassword(plain: string): Promise<string>;
  verifyPassword(plain: string, hashed: string): Promise<boolean>;
}
```

#### 4d. Config provider

**Python — `providers/config.py`:**

```python
"""Abstract config provider — domains depend on this, not on os.environ/etc."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConfigProvider(Protocol):
    """Key-value configuration interface.

    Concrete implementations read from environment variables, Vault, AWS SSM,
    or any other backing store.  Test doubles can serve hard-coded values.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, or *default* if not set."""
        ...

    def require(self, key: str) -> Any:
        """Return the value for *key*.

        Raises ConfigurationError if the key is not set.
        """
        ...

    def get_bool(self, key: str, default: bool = False) -> bool: ...
    def get_int(self, key: str, default: int = 0) -> int: ...
```

**JS/TS — `src/providers/config.ts`:**

```ts
/** Abstract config provider — domains depend on this, not on process.env/dotenv/etc. */
export interface ConfigProvider {
  get(key: string, defaultValue?: string): string | undefined;
  require(key: string): string;
  getBool(key: string, defaultValue?: boolean): boolean;
  getInt(key: string, defaultValue?: number): number;
}
```

---

### Step 5: Generate concrete adapter implementations

Create `providers/impl/` with ready-to-use adapters for the libraries detected in Step 2.
Only generate adapters for libraries that are actually present in the project.

Check for installed libraries before generating each adapter:

```bash
# Python — check pyproject.toml / requirements.txt
grep -E "structlog|loguru|logging|jwt|passlib|pydantic.settings|dynaconf" \
  pyproject.toml requirements*.txt 2>/dev/null

# JS/TS — check package.json
grep -E '"winston"|"pino"|"jsonwebtoken"|"jose"|"bcrypt"|"dotenv"' package.json 2>/dev/null
```

Generate only the adapters whose libraries are installed.  Example adapters:

**`providers/impl/structlog_logging.py`** (generated when `structlog` is detected):

```python
"""Concrete LoggingProvider backed by structlog."""

from __future__ import annotations

from typing import Any

import structlog

from providers.logging import LoggingProvider


class StructlogProvider:
    """Wraps structlog to satisfy the LoggingProvider protocol."""

    def __init__(self, logger: Any | None = None) -> None:
        self._log = logger or structlog.get_logger()

    def debug(self, message: str, **context: Any) -> None:
        self._log.debug(message, **context)

    def info(self, message: str, **context: Any) -> None:
        self._log.info(message, **context)

    def warning(self, message: str, **context: Any) -> None:
        self._log.warning(message, **context)

    def error(self, message: str, **context: Any) -> None:
        self._log.error(message, **context)

    def critical(self, message: str, **context: Any) -> None:
        self._log.critical(message, **context)

    def bind(self, **context: Any) -> "StructlogProvider":
        return StructlogProvider(self._log.bind(**context))


# Satisfy the protocol at import time so mypy and runtime checks both pass.
_: LoggingProvider = StructlogProvider()  # type: ignore[assignment]
```

**`providers/impl/__init__.py`** — re-export all concrete adapters:

```python
"""Concrete provider implementations.

Wire these up at application startup.  Example::

    from providers.impl import StructlogProvider, JWTAuthProvider, EnvConfigProvider
    from providers import LoggingProvider, AuthProvider, ConfigProvider

    logger: LoggingProvider = StructlogProvider()
    auth:   AuthProvider    = JWTAuthProvider(secret=config.require("JWT_SECRET"))
    config: ConfigProvider  = EnvConfigProvider()
"""
# (imports added dynamically based on which adapters were generated)
```

Each adapter file follows the same pattern:
1. Import only from the concrete library and the abstract provider interface.
2. Implement every method defined in the Protocol / Interface.
3. Add a `_: ProviderType = ConcreteClass()` line to verify protocol satisfaction.

---

### Step 6: Preview and confirm file writes

Before writing any file, print a diff-style preview:

```
  [New file] providers/__init__.py          (35 lines)
  [New file] providers/logging.py           (28 lines)
  [New file] providers/auth.py              (36 lines)
  [New file] providers/config.py            (29 lines)
  [New file] providers/impl/__init__.py     (18 lines)
  [New file] providers/impl/structlog_logging.py  (46 lines)

  Write these files? [y/N]
```

Do **not** write if `--dry-run` is active or the engineer answers N.

---

### Step 7: Write provider principles to `.claude/principles.yaml`

Load `.claude/principles.yaml` (create if missing).  Upsert principles with IDs
`CP001`–`CP999` (CP = cross-cutting provider).  Do not duplicate existing IDs.

```yaml
# Generated by /providers-pattern — do not edit IDs manually

- id: "CP001"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Logging: domains must import LoggingProvider from `providers`, never import
    structlog, loguru, logging, winston, pino, or bunyan directly.
    Violation example: `import structlog` inside an application domain module.

- id: "CP002"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Auth: domains must import AuthProvider from `providers`, never import
    jwt, jose, passlib, authlib, bcrypt, jsonwebtoken, or similar directly.
    Violation example: `from jose import jwt` inside an application domain module.

- id: "CP003"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Config: domains must import ConfigProvider from `providers`, never read
    os.environ, process.env, or import pydantic_settings/dynaconf/dotenv directly.
    Violation example: `import os; os.environ["DB_URL"]` inside a domain module.

- id: "CP004"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    The `providers/` package and `providers/impl/` are the only permitted locations
    for concrete cross-cutting library imports.  No other package may import
    structlog, jwt, os.environ, or equivalent directly.
```

Rules:
- Only write principles for the concern categories that had at least one violation detected
  in Step 2.  If zero logging violations were found, skip CP001.
- Re-running `/providers-pattern` updates existing `CP*` principles in-place; it never
  duplicates them.
- After writing, also regenerate `docs/PRINCIPLES.md` (same logic as `/define-principles`
  Step 4.5).

---

### Step 8: Migration hints for existing violations

For every violation recorded in Step 2, emit a concise migration hint so engineers know
how to fix each callsite:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Migration Hints  (apply manually or use your editor's rename tool)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  orders/service.py
  ─────────────────
  Before:  import structlog
           logger = structlog.get_logger()
           logger.info("order created", order_id=order_id)

  After:   # inject via constructor or service locator
           from providers import LoggingProvider

           class OrderService:
               def __init__(self, logger: LoggingProvider) -> None:
                   self._logger = logger

               def create_order(self, ...) -> ...:
                   self._logger.info("order created", order_id=order_id)

  ─────────────────
  orders/checkout.py
  ─────────────────
  Before:  from jose import jwt
           token = jwt.encode(claims, secret, algorithm="HS256")
           decoded = jwt.decode(token, secret, algorithms=["HS256"])

  After:   from providers import AuthProvider

           class CheckoutService:
               def __init__(self, auth: AuthProvider) -> None:
                   self._auth = auth

               def issue_session_token(self, user_id: str) -> str:
                   return self._auth.create_token(subject=user_id)

  (... one hint per unique file+concern combination ...)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 9: Final summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Providers Pattern — Done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Domains scanned:          5
  Violations found:        11  (6 logging · 4 auth · 1 config)
  Clean domains:            1  (users ✅)

  Files written:
    providers/__init__.py
    providers/logging.py
    providers/auth.py
    providers/config.py
    providers/impl/__init__.py
    providers/impl/structlog_logging.py     ← structlog detected
    providers/impl/jwt_auth.py             ← jose detected
    providers/impl/env_config.py           ← pydantic-settings detected

  Principles written → .claude/principles.yaml  (CP001–CP004)
  docs/PRINCIPLES.md regenerated

  Enforcement active in:
    • /check-code  — flags direct cross-cutting imports in staged files
    • /review-pr   — flags violations in PR diffs under CP001–CP004

  Next steps:
    1. Wire up concrete providers at application startup (see providers/impl/).
    2. Apply migration hints above to each violation callsite.
    3. Run /check-code to verify no violations remain.
    4. Commit with /checkpoint once all domains are clean.

  Re-run any time:         /providers-pattern
  Scan only, no writes:    /providers-pattern --dry-run
  Single concern:          /providers-pattern --concern logging
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--dry-run` | Scan and report only — no files written, no principles updated |
| `--concern <name>` | Limit scan and generation to one concern: `logging`, `auth`, or `config` |
| `--domain <path>` | Scan a single domain package instead of the whole project |
| `--fix` | Apply all file writes without interactive confirmation |
| `--no-impl` | Generate provider interfaces only; skip the `providers/impl/` adapters |
| `--no-principles` | Skip Step 7 (don't write to `.claude/principles.yaml`) |
| `--no-hints` | Suppress per-callsite migration hints in the output |

---

## Notes

- **Safe to re-run**: existing provider files are shown as diffs, not silently overwritten.
  `CP*` principles are upserted, never duplicated.
- **Does not commit**: stage and commit generated files with `/checkpoint` or manually.
- **Test doubles**: the generated Protocol / Interface is mockable out of the box.  In
  `conftest.py` / `vitest.setup.ts`, substitute a no-op or spy implementation — no
  patching of third-party modules required.
- **Monorepos**: run with `--domain` to handle one domain at a time, or run at the
  repo root to generate a shared `providers/` package that all domains can depend on.
- **Whitelisted locations**: `providers/impl/` and application entry-points (`app.py`,
  `main.py`, `index.ts`, `server.ts`) are excluded from the violation scan because
  those are the intended sites for concrete library imports.
- **`os` in Python**: bare `import os` is flagged only when followed by `os.environ`
  access.  Usage of `os.path`, `os.getcwd()`, etc. is not flagged.
- **Complements `/module-boundaries`**: both skills write to `.claude/principles.yaml`
  using different ID ranges (`MB*` vs `CP*`).  Run both for full architectural coverage.

---

## Related skills

| Scenario | Skill |
|---|---|
| Enforce explicit module public surfaces | `/module-boundaries` |
| Add or edit architectural golden rules manually | `/define-principles` |
| Run all quality gates on staged changes | `/check-code` |
| Review a PR against all active principles | `/review-pr` |
| Check for cross-agent task conflicts | `/coordinate` |
