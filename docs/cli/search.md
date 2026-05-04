# harness search

> Symbol-level lookup over the harness symbol index.

`search` queries `harness_symbols.json` — a flat index of the project's functions, classes, methods, and constants produced by the symbol indexer. Unlike text-grep, it returns *typed* symbol matches (function vs class vs constant) with their fully-qualified names and source-file locations, suitable for an agent to read or jump to.

Pair with [`harness context`](context.md) for a complete lookup loop: `context` finds files; `search` finds symbols.

## Synopsis

```bash
harness search QUERY [OPTIONS]
```

## Arguments

| Argument | Type | Description |
|---|---|---|
| `QUERY` | str (positional) | Substring or pattern to match against symbol names. |

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--symbols-file` | path | `harness_symbols.json` | Symbol-index file. Produced and refreshed by the symbol indexer (see Notes). |
| `--type` | choice (`function` / `class` / `method` / `constant` / `all`) | `all` | Filter by symbol kind. |
| `--max-results` | int | `20` | Cap the result list. |
| `--output-format` | choice (`json` / `text`) | TTY-aware | Output format. JSON includes file paths and line numbers per match. |

## Workflows

### Find a function by partial name

```bash
harness search authenticate --type function --max-results 5
```

### List every class whose name contains "Validator"

```bash
harness search Validator --type class --output-format json | jq '.matches[].qualified_name'
```

### Cross-reference a symbol you saw in logs

```bash
# saw "calling user_session.refresh()" in observe output
harness search refresh --type method --output-format json
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | At least one match found. |
| `1` | No matches. |
| `2` | Internal error — symbols file missing / unreadable / not JSON. |

## Notes

- `harness_symbols.json` is gitignored (it's a generated artifact, similar to `__pycache__/`). Refresh it via the harness symbol-index skill or whatever step your project uses to generate it; it isn't (re)built automatically by `search` itself.

## See also

- [`harness context`](context.md) — file-level discovery; complementary to `search`'s symbol-level view.
- [`harness observe`](observe.md) — when log output references a symbol, `search` to find where it's defined.
