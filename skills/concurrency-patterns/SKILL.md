---
name: concurrency-patterns
description: "Scans the codebase for async/await patterns, thread-safety mechanisms, and pool usage, then generates framework-specific concurrency rules and code snippets matched to the detected conventions. Detects: anyio, asyncio (stdlib), threading, concurrent.futures, aiohttp, httpx. Flags anti-patterns: blocking calls (time.sleep, requests.get) inside async functions, missing in-memory locks for shared mutable state, bare thread spawns without join, deprecated asyncio.get_event_loop(). Generates ready-to-paste code snippets for: anyio TaskGroup, asyncio.TaskGroup, asyncio.Lock / anyio.Lock, ThreadPoolExecutor with correct sizing, run_sync / run_in_executor for bridging sync code, fcntl.LOCK_EX for cross-process file safety. Use when: (1) starting work in an async codebase and need to know the team's conventions, (2) reviewing a PR that adds concurrency primitives, (3) a linter or code-review agent needs concrete async/thread-safety rules, (4) debugging a suspected race condition or blocking-in-async bug, (5) on-boarding a new async pattern (task group, semaphore, pool) into an existing service. Triggers on: async pattern, concurrency rules, thread safety, async/await conventions, pool usage, blocking in async, asyncio rules, anyio rules, task group, semaphore, lock, executor, aiohttp, httpx, detect async framework, concurrency anti-patterns."
---

# Concurrency & Async Pattern Analyzer

## Overview

The **concurrency-patterns** skill inspects the project's Python source files,
identifies which concurrency model is in use (anyio, asyncio, threading, or sync),
flags anti-patterns that cause hard-to-debug bugs, and generates framework-appropriate
rules with ready-to-paste code snippets.

| Capability | Description |
|------------|-------------|
| Framework detection | anyio, asyncio, threading, concurrent.futures, or sync |
| Anti-pattern detection | Blocking calls in async, missing locks, bare thread spawns, deprecated APIs |
| Rule generation | Framework-matched snippets for task groups, locks, pools, sync bridges |
| Severity levels | error, warning, info |
| Output formats | Human-readable table or JSON |

---

## Workflow

**Do you want to know which async framework the project uses?**
-> [Framework detection](#framework-detection)

**Do you want to find concurrency bugs or anti-patterns?**
-> [Violation scanning](#violation-scanning)

**Do you want a code snippet for a specific pattern?**
-> [Pattern snippets](#pattern-snippets)

**Do you want a full report (framework + rules + violations)?**
-> [Full analysis](#full-analysis)

---

## Framework Detection

```bash
python skills/concurrency_patterns.py detect --path src/
```

Output:
```
Detected framework: anyio
  Signals: 12 anyio imports, 5 create_task_group usages, 3 async def
```

---

## Violation Scanning

```bash
# Show only anti-patterns found in the codebase
python skills/concurrency_patterns.py detect --violations-only
```

Example violations reported:
```
VIOLATION  src/worker.py:42   blocking-call-in-async   time.sleep(5) inside async def; use 'await anyio.sleep(5)'
VIOLATION  src/api.py:87      blocking-call-in-async   requests.get(...) inside async def; use httpx.AsyncClient
WARNING    src/cache.py:19    missing-async-lock       shared dict mutated in async def without asyncio.Lock / anyio.Lock
```

---

## Pattern Snippets

```bash
# List all available pattern names
python skills/concurrency_patterns.py list-patterns

# Print a ready-to-paste snippet
python skills/concurrency_patterns.py snippet --pattern anyio-task-group
python skills/concurrency_patterns.py snippet --pattern asyncio-lock
python skills/concurrency_patterns.py snippet --pattern thread-pool
python skills/concurrency_patterns.py snippet --pattern run-sync-in-thread
python skills/concurrency_patterns.py snippet --pattern fcntl-file-lock
```

---

## Full Analysis

```bash
# Detect framework, generate rules, and scan for violations
python skills/concurrency_patterns.py detect

# JSON output for programmatic consumption
python skills/concurrency_patterns.py detect --json
```

---

## Programmatic Use

```python
from pathlib import Path
from skills.concurrency_patterns import ConcurrencyAnalyzer

analyzer = ConcurrencyAnalyzer(root=Path("src/"))
report = analyzer.analyze()

print(report.framework)           # "anyio" | "asyncio" | "threading" | "sync"
print(report.stats)               # {"async_def_count": 42, "await_count": 87, ...}

for rule in report.rules:
    print(rule.name, rule.severity, rule.description)
    print(rule.snippet)           # ready-to-paste code

for v in report.violations:
    print(v.file, v.line, v.rule_name, v.message)
    if v.snippet_fix:
        print("Fix:", v.snippet_fix)
```

---

## Generated Rules Reference

### anyio rules

| Rule | Severity | Description |
|------|----------|-------------|
| `anyio-task-group` | info | Use `anyio.create_task_group()` for structured concurrency |
| `anyio-lock` | info | Use `anyio.Lock()` to guard shared mutable state in async code |
| `anyio-sleep` | error | Replace `time.sleep(n)` with `await anyio.sleep(n)` in async functions |
| `anyio-run-sync` | warning | Use `await anyio.to_thread.run_sync(fn)` to offload blocking sync calls |
| `anyio-cancel-scope` | info | Use `anyio.CancelScope(deadline=...)` for timeout-bounded operations |

### asyncio rules

| Rule | Severity | Description |
|------|----------|-------------|
| `asyncio-task-group` | info | Use `asyncio.TaskGroup` (3.11+) or `asyncio.gather` for concurrent tasks |
| `asyncio-lock` | info | Use `asyncio.Lock()` to guard shared mutable state |
| `asyncio-sleep` | error | Replace `time.sleep(n)` with `await asyncio.sleep(n)` in async functions |
| `asyncio-run-in-executor` | warning | Use `loop.run_in_executor(None, fn)` to offload blocking sync calls |
| `asyncio-get-running-loop` | warning | Replace deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()` |

### threading rules

| Rule | Severity | Description |
|------|----------|-------------|
| `thread-lock-context` | info | Use `threading.Lock()` as a context manager (`with lock:`) |
| `thread-pool-sizing` | warning | Size `ThreadPoolExecutor(max_workers=...)` explicitly; I/O-bound: cpu+4, CPU-bound: cpu |
| `thread-join-required` | error | Every `Thread(...).start()` must be paired with `.join()` or use a pool |
| `thread-rlock-reentrant` | info | Use `threading.RLock()` when the same thread may acquire the lock recursively |

### sync / multi-process rules

| Rule | Severity | Description |
|------|----------|-------------|
| `fcntl-file-lock` | info | Use `fcntl.LOCK_EX` for exclusive cross-process file writes |
| `atomic-rename` | info | Use `tmp.replace(target)` (POSIX atomic) for safe file updates |
| `o-creat-excl-lock` | info | Use `os.O_CREAT | os.O_EXCL` for atomic lock file creation |

---

## Anti-Pattern Detection Reference

| Anti-pattern | Detected by | Severity |
|---|---|---|
| `time.sleep(` inside `async def` | Regex scan | error |
| `requests.get/post/put/delete(` inside `async def` | Regex scan | error |
| `open(` for write inside `async def` without `await` | Regex scan | warning |
| `asyncio.get_event_loop()` (deprecated) | Regex scan | warning |
| `Thread(...).start()` without `.join()` | Heuristic scan | error |
| Shared mutable assignment inside `async def` without lock | Heuristic scan | warning |

---

## Key Files

| Path | Purpose |
|------|---------|
| `skills/concurrency_patterns.py` | Full implementation — `ConcurrencyAnalyzer`, `PatternRule`, `Violation`, `ConcurrencyReport`, CLI. |
| `skills/concurrency-patterns/SKILL.md` | This document — agent routing metadata and usage guide. |
| `tests/test_concurrency_patterns.py` | pytest test suite for the analyzer. |
