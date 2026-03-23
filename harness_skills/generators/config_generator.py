"""
harness_skills/generators/config_generator.py
===============================================
Skill that generates per-gate YAML configuration for ``harness.config.yaml``.

Engineers call ``generate_gate_config(profile)`` to get a complete ``gates:``
section pre-populated with profile-appropriate defaults and inline comments.
Call ``write_harness_config(path, profile)`` to merge it into an existing file
without disturbing surrounding keys or comments.

Public API
----------
    generate_gate_config(profile, detected_stack)  ->  str  (YAML text)
    write_harness_config(path, profile, detected_stack, *, merge)

Usage::

    from harness_skills.generators.config_generator import generate_gate_config
    print(generate_gate_config("standard", detected_stack="python"))

    from harness_skills.generators.config_generator import write_harness_config
    write_harness_config("harness.config.yaml", profile="standard")
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from harness_skills.models.gate_configs import (
    ArchitectureGateConfig,
    CoverageGateConfig,
    DocsFreshnessGateConfig,
    LintGateConfig,
    PerformanceGateConfig,
    PrinciplesGateConfig,
    RegressionGateConfig,
    SecurityGateConfig,
    TypesGateConfig,
    PROFILE_GATE_DEFAULTS,
)

_VALID_PROFILES = frozenset({"starter", "standard", "advanced"})

_COVERAGE_TOOL_HINT: dict[str | None, str] = {
    "python": "# tool: coverage.py  (pytest --cov . --cov-report=json)",
    "node":   "# tool: jest --coverage",
    "go":     "# tool: go test -coverprofile=coverage.out ./...",
    None:     "# tool: auto-detected from project files",
}

_GATE_ORDER = [
    "regression", "coverage", "security", "performance",
    "architecture", "principles", "docs_freshness", "types", "lint",
]

# NOTE: leading whitespace is intentional — keeps plugins: at the same 6-space
# indentation level as all other gate keys in the generated YAML fragment.
_PLUGIN_COMMENT = (
    "      # ── Custom plugin gates ─────────────────────────────────────────────\n"
    "      # Each entry runs a shell command; exit code 0=pass, non-zero=fail.\n"
    "      # Required: gate_id, gate_name, command\n"
    "      # Optional: timeout_seconds (60), fail_on_error (true), severity (error), env ({})\n"
    "      #\n"
    "      # Example:\n"
    "      #   plugins:\n"
    "      #     - gate_id: check_migrations\n"
    '      #       gate_name: "DB Migration Safety"\n'
    '      #       command: "python scripts/check_migrations.py"\n'
    "      #       timeout_seconds: 30\n"
    "      #       fail_on_error: true\n"
    "      plugins: []                       # replace [] with gate definitions"
)


def _b(v: bool) -> str:
    return "true" if v else "false"


def _render_regression(cfg: RegressionGateConfig) -> str:
    args = repr(cfg.extra_args) if cfg.extra_args else "[]"
    return (
        "      regression:                       # Run the test suite (pytest / jest)\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        timeout_seconds: {cfg.timeout_seconds}"
        "            # max wall-clock seconds for the full suite\n"
        f"        extra_args: {args}"
        "                  # e.g. ['--tb=short', '-x']\n"
    )


def _render_coverage(cfg: CoverageGateConfig, detected_stack: str | None) -> str:
    tool_hint = _COVERAGE_TOOL_HINT.get(detected_stack, _COVERAGE_TOOL_HINT[None])
    pats = repr(cfg.exclude_patterns) if cfg.exclude_patterns else "[]"
    return (
        "      coverage:                         # Enforce minimum line-coverage %\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        threshold: {cfg.threshold}                   {tool_hint}\n"
        "                                       # % minimum project-wide line coverage\n"
        f"        branch_coverage: {_b(cfg.branch_coverage)}"
        "          # measure condition coverage too (pytest-cov >= 4)\n"
        f"        exclude_patterns: {pats}"
        "            # e.g. ['tests/', 'migrations/']\n"
    )


def _render_security(cfg: SecurityGateConfig) -> str:
    ids = repr(cfg.ignore_ids) if cfg.ignore_ids else "[]"
    return (
        "      security:                         # pip-audit CVEs + bandit static analysis\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        severity_threshold: {cfg.severity_threshold}"
        "        # CRITICAL | HIGH | MEDIUM | LOW\n"
        f"        scan_dependencies: {_b(cfg.scan_dependencies)}"
        "         # run pip-audit / npm audit\n"
        f"        scan_secrets: {_b(cfg.scan_secrets)}"
        "             # detect hardcoded API keys / tokens\n"
        f"        ignore_ids: {ids}"
        "                   # e.g. ['CVE-2023-12345', 'B101']\n"
    )


def _render_performance(cfg: PerformanceGateConfig) -> str:
    note = (
        "        # Requires .harness-perf.sh benchmark script\n"
        if not cfg.enabled else ""
    )
    return (
        "      performance:                      # Time .harness-perf.sh vs. budget_ms\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        + note
        + f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        budget_ms: {cfg.budget_ms}"
        "                  # P95 response-time ceiling in ms\n"
        f"        regression_threshold_pct: {cfg.regression_threshold_pct}"
        "   # max % degradation vs. baseline\n"
    )


def _render_architecture(cfg: ArchitectureGateConfig) -> str:
    rules = "\n".join(f"          - {r}" for r in cfg.rules)
    out = (
        "      architecture:                     # Import layer-violation detection (AST)\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        rules:\n{rules}\n"
    )
    if cfg.layer_definitions:
        # Fully custom layer definitions with aliases take highest priority
        out += "        layer_definitions:            # custom layers; overrides arch_style and layer_order\n"
        for ld in cfg.layer_definitions:
            aliases = ld.get("aliases", [])
            out += f"          - name: {ld['name']}\n"
            out += f"            rank: {ld.get('rank', 0)}\n"
            if aliases:
                out += "            aliases:\n"
                for alias in aliases:
                    out += f"              - {alias}\n"
    elif cfg.arch_style:
        # Named preset — use arch_style instead of layer_order
        out += (
            f"        arch_style: {cfg.arch_style}"
            "              # clean | hexagonal | mvc | ddd | layered\n"
        )
    else:
        # Backward-compatible plain layer_order list
        layers = ", ".join(cfg.layer_order)
        out += (
            f"        layer_order: [{layers}]"
            "          # or use arch_style / layer_definitions for richer control\n"
        )
    out += (
        f"        report_only: {_b(cfg.report_only)}"
        "            # set true to warn without failing\n"
    )
    return out


def _render_principles(cfg: PrinciplesGateConfig) -> str:
    rules = "\n".join(f"          - {r}" for r in cfg.rules)
    note = (
        "        # advisory warnings — non-blocking by default\n"
        if not cfg.fail_on_error else ""
    )
    return (
        "      principles:                       # Scan for coding-principle violations\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        + note
        + f"        principles_file: {cfg.principles_file}\n"
        f"        rules:\n{rules}\n"
    )


def _render_docs_freshness(cfg: DocsFreshnessGateConfig) -> str:
    files = "\n".join(f"          - {f}" for f in cfg.tracked_files)
    return (
        "      docs_freshness:                   # Flag stale harness-generated artifacts\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        max_staleness_days: {cfg.max_staleness_days}"
        "          # flag docs older than this many days\n"
        f"        tracked_files:\n{files}\n"
    )


def _render_types(cfg: TypesGateConfig) -> str:
    errs = repr(cfg.ignore_errors) if cfg.ignore_errors else "[]"
    strict_note = (
        "        # strict: true = mypy --strict / pyright strict\n"
        if cfg.strict else
        "        # set strict: true for mypy --strict / pyright strict\n"
    )
    return (
        "      types:                            # Static type checking (mypy / tsc --noEmit)\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        strict: {_b(cfg.strict)}\n"
        + strict_note
        + f"        ignore_errors: {errs}"
        "          # e.g. ['misc', 'import-untyped']\n"
    )


def _render_lint(cfg: LintGateConfig) -> str:
    sel = repr(cfg.select) if cfg.select else "[]"
    ign = repr(cfg.ignore) if cfg.ignore else "[]"
    return (
        "      lint:                             # Linting (ruff / eslint / golangci-lint)\n"
        f"        enabled: {_b(cfg.enabled)}\n"
        f"        fail_on_error: {_b(cfg.fail_on_error)}\n"
        f"        autofix: {_b(cfg.autofix)}"
        "             # attempt ruff --fix / eslint --fix before reporting\n"
        f"        select: {sel}"
        "                    # empty = tool defaults\n"
        f"        ignore: {ign}"
        "                    # e.g. ['E501'] for line-length\n"
    )


def _render_gate(gate_id: str, cfg: object, detected_stack: str | None) -> str:
    """Dispatch to the appropriate per-gate YAML renderer."""
    if isinstance(cfg, RegressionGateConfig):    return _render_regression(cfg)
    if isinstance(cfg, CoverageGateConfig):      return _render_coverage(cfg, detected_stack)
    if isinstance(cfg, SecurityGateConfig):      return _render_security(cfg)
    if isinstance(cfg, PerformanceGateConfig):   return _render_performance(cfg)
    if isinstance(cfg, ArchitectureGateConfig):  return _render_architecture(cfg)
    if isinstance(cfg, PrinciplesGateConfig):    return _render_principles(cfg)
    if isinstance(cfg, DocsFreshnessGateConfig): return _render_docs_freshness(cfg)
    if isinstance(cfg, TypesGateConfig):         return _render_types(cfg)
    if isinstance(cfg, LintGateConfig):          return _render_lint(cfg)
    return f"      {gate_id}:\n        enabled: true\n"


def generate_gate_config(
    profile: str,
    detected_stack: str | None = None,
) -> str:
    """Generate a complete ``gates:`` YAML block for a harness profile.

    Every threshold field includes an inline comment explaining its purpose.
    The output can be pasted directly under ``profiles.<profile>:`` in
    ``harness.config.yaml``.

    Parameters
    ----------
    profile:
        One of ``"starter"``, ``"standard"``, or ``"advanced"``.
    detected_stack:
        Optional hint — ``"python"``, ``"node"``, or ``"go"`` — used to
        tailor coverage-tool comments.

    Returns
    -------
    str
        YAML text for the complete ``gates:`` block (indented 4 spaces).

    Raises
    ------
    ValueError
        If *profile* is not recognised.

    Examples
    --------
    ::

        from harness_skills.generators.config_generator import generate_gate_config
        print(generate_gate_config("standard", detected_stack="python"))
    """
    if profile not in _VALID_PROFILES:
        raise ValueError(
            f"Unknown profile {profile!r}. Valid: {sorted(_VALID_PROFILES)}"
        )

    defaults = PROFILE_GATE_DEFAULTS[profile]
    parts = [
        "    gates:",
        "      # Each gate: enabled/fail_on_error + gate-specific thresholds.",
        "      # Set enabled: false to skip; fail_on_error: false for advisory mode.",
    ]

    for gate_id in _GATE_ORDER:
        cfg = defaults.get(gate_id)
        if cfg is None:
            continue
        parts.append("")
        parts.append(_render_gate(gate_id, cfg, detected_stack).rstrip())

    parts.append("")
    parts.append(_PLUGIN_COMMENT)
    return "\n".join(parts) + "\n"


def write_harness_config(
    path: str | Path,
    profile: str,
    detected_stack: str | None = None,
    *,
    merge: bool = True,
) -> None:
    """Write (or merge) per-gate config into ``harness.config.yaml``.

    Parameters
    ----------
    path:
        Filesystem path to ``harness.config.yaml``.
    profile:
        Profile whose ``gates:`` block to update.
    detected_stack:
        Optional stack hint forwarded to :func:`generate_gate_config`.
    merge:
        ``True`` (default) — replace only ``profiles.<profile>.gates``,
        preserving all other keys and comments.
        ``False`` — overwrite the file with a minimal new config.

    Raises
    ------
    ValueError
        If *profile* is unrecognised.
    FileNotFoundError
        If *merge=True* and *path* does not exist.
    """
    path = Path(path)
    gates_yaml = generate_gate_config(profile, detected_stack)

    if not merge:
        path.write_text(_build_minimal_config(profile, gates_yaml), encoding="utf-8")
        return

    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Pass merge=False to create from scratch."
        )

    try:
        _merge_with_ruamel(path, profile, gates_yaml)
    except ImportError:
        _merge_with_regex(path, profile, gates_yaml)


def _merge_with_ruamel(path: Path, profile: str, gates_yaml: str) -> None:
    """Merge using ruamel.yaml (preserves all existing comments)."""
    from ruamel.yaml import YAML  # type: ignore[import]
    import io as _io
    import yaml as pyyaml  # type: ignore[import]

    yaml = YAML()
    yaml.preserve_quotes = True
    with path.open("r", encoding="utf-8") as fh:
        doc: Any = yaml.load(fh)

    gates_doc: Any = pyyaml.safe_load(gates_yaml)
    new_gates = gates_doc.get("gates", {}) if gates_doc else {}
    doc.setdefault("profiles", {})
    doc["profiles"].setdefault(profile, {})
    doc["profiles"][profile]["gates"] = new_gates

    buf = _io.StringIO()
    yaml.dump(doc, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")


def _merge_with_regex(path: Path, profile: str, gates_yaml: str) -> None:
    """Splice the gates block using line-by-line search (no ruamel dependency)."""
    import re

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    in_profiles = False
    profile_start = -1
    for i, line in enumerate(lines):
        if line.strip() == "profiles:":
            in_profiles = True
            continue
        if in_profiles:
            if re.match(rf"^\s{{2}}{re.escape(profile)}:", line):
                profile_start = i
                break
            if line.strip() and not line.startswith(" "):
                in_profiles = False

    if profile_start == -1:
        path.write_text(original + "\n" + gates_yaml, encoding="utf-8")
        return

    gates_start = gates_end = -1
    i = profile_start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() and re.match(r"^\s{2}\S", line):
            break
        if re.match(r"^\s{4}gates:", line):
            gates_start = i
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and re.match(r"^\s{4}\S", lines[j]):
                    gates_end = j
                    break
                j += 1
            if gates_end == -1:
                gates_end = j
            break
        i += 1

    new_lines = gates_yaml.splitlines(keepends=True)
    if gates_start == -1:
        out = lines[:profile_start + 1] + new_lines + lines[profile_start + 1:]
    else:
        out = lines[:gates_start] + new_lines + lines[gates_end:]
    path.write_text("".join(out), encoding="utf-8")


def _build_minimal_config(profile: str, gates_yaml: str) -> str:
    return (
        f"# harness.config.yaml — generated by harness config generate\n"
        f"active_profile: {profile}\n\n"
        f"profiles:\n"
        f"  {profile}:\n"
        f"    description: >\n"
        f"      Auto-generated {profile} profile.\n\n"
        f"{gates_yaml}\n"
        f"    documentation:\n"
        f"      auto_generate: true\n"
        f"      formats:\n"
        f"        - markdown\n"
    )
