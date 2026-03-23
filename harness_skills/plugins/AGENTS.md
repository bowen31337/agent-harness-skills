# AGENTS.md — harness_skills.plugins

## Purpose

Custom evaluation gate plugin system. Allows project teams to define and run project-specific quality gates entirely in `harness.config.yaml` under each profile's `gates.plugins` list — no Python code changes required. Plugins shell-out to arbitrary commands and interpret their exit codes and stdout as pass/fail results.

---

## Key Files

| File | Exports | Description |
|------|---------|-------------|
| `gate_plugin.py` | `PluginGateConfig`, `PluginGateRunner` | Validated gate descriptor (Pydantic model) and single-gate executor |
| `loader.py` | `load_plugin_gates` | Reads the `gates.plugins` list from a profile config dict and returns `list[PluginGateConfig]` |
| `runner.py` | `run_plugin_gates` | Executes all loaded plugin gates and collects `GateResult` objects |
| `__init__.py` | `PluginGateConfig`, `PluginGateRunner`, `load_plugin_gates`, `run_plugin_gates` | Public API surface |

---

## Internal Patterns

- **YAML-driven configuration** — plugin gates are defined in `harness.config.yaml`; the loader validates them against `PluginGateConfig`.
- **Shell command execution** — `PluginGateRunner` spawns a subprocess for each gate; exit code `0` = pass, non-zero = failure.
- **Structured output parsing** — stdout from the plugin command is parsed (JSON or plain text) to populate `GateResult.violations`.
- **Fail-safe** — if a plugin command times out or crashes, `run_plugin_gates` records it as a gate failure rather than propagating the exception.
- **No Python required** — the entire plugin contract is: command string + optional timeout + severity level in YAML.

---

## Domain-Specific Constraints

- **Plugins must not be imported by `gates/` built-in runners** — the dependency direction is: `plugins` depends on `models`, not on `gates`.
- **`PluginGateConfig` is the only validated entry-point** — raw dicts from YAML must always pass through `load_plugin_gates` before execution.
- **Command injection prevention** — plugin command strings are passed to `subprocess` with `shell=False` and argument splitting; never use `shell=True`.
- **Timeout is mandatory** — every `PluginGateConfig` must carry a `timeout_seconds` value; the loader must reject entries missing this field.
- **Principle MB008** — `plugins` package may import from `models` only; never from `gates`, `cli`, or `generators`.
