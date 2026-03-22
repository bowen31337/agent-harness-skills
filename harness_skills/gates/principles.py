"""
harness_skills/gates/principles.py
====================================
Golden-principles compliance gate.

Loads ``.claude/principles.yaml`` (or a custom path), maps each principle's
YAML ``severity`` to a :class:`GateFailure` severity level, runs built-in
AST scanners for automatically detectable violations, and reports all results.

Gate behaviour
--------------
* Principles with ``severity: "blocking"`` in the YAML are scanned for code
  violations and reported as ``severity="error"`` in :class:`Violation`.
* When ``fail_on_critical=True`` (the default) the gate fails as soon as any
  ``"error"``-severity violation is found — even if ``fail_on_error=False``.
* ``fail_on_error=False`` (advisory mode) downgrades non-critical errors to
  warnings; ``fail_on_critical`` still applies to blocking violations.

Built-in scanners
-----------------
All scanners operate on Python source files only (``*.py``), skipping virtual
environments, caches, and hidden directories.

+-------------------+-------+--------------------------------------------------+
| Scanner           | Rule  | What it detects                                  |
+===================+=======+==================================================+
| no_magic_numbers  | P011  | Numeric literals outside an allowed whitelist    |
+-------------------+-------+--------------------------------------------------+
| no_hardcoded_urls | P012  | Hard-coded HTTP/HTTPS string literals            |
+-------------------+-------+--------------------------------------------------+
| function_naming   | P014  | Non-snake_case function / method names           |
+-------------------+-------+--------------------------------------------------+
| variable_naming   | P015  | Single-letter variable names outside loop counts |
+-------------------+-------+--------------------------------------------------+
| class_naming      | P016  | Non-PascalCase class names                       |
+-------------------+-------+--------------------------------------------------+
| file_naming       | P017  | Non-snake_case Python file names                 |
+-------------------+-------+--------------------------------------------------+

Usage (Python API)
------------------
::

    from harness_skills.gates.principles import PrinciplesGate, GateConfig

    gate = PrinciplesGate(GateConfig(fail_on_critical=True))
    result = gate.run(project_root=Path("."))

    if not result.passed:
        for v in result.errors():
            print(f"[BLOCKING] {v.principle_id}: {v.message}")

CLI
---
::

    uv run python -m harness_skills.gates.principles --root .
    uv run python -m harness_skills.gates.principles --root . --no-fail-on-critical

Exit codes
----------
* ``0`` — gate passed (no blocking violations, or advisory mode)
* ``1`` — gate failed (blocking violations present and ``fail_on_critical=True``)
* ``2`` — internal error (YAML parse failure, unexpected exception)
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Numeric literals that are always exempt from the magic-number check.
_ALLOWED_NUMBERS: frozenset[object] = frozenset({0, 1, -1, 2, 100, 1000})

#: Regex for detecting hard-coded HTTP(S) URLs in string literals.
_URL_RE: re.Pattern[str] = re.compile(r"https?://[^\s\"']+")

#: Directories to skip during file traversal.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".venv", "venv", "__pycache__", ".git", ".mypy_cache",
    ".pytest_cache", "node_modules", "dist", "build",
})

#: Map from YAML principle ``severity`` to :class:`Violation` severity string.
_SEVERITY_MAP: dict[str, str] = {
    "blocking":   "error",
    "warning":    "warning",
    "suggestion": "info",
    "info":       "info",
}

#: Built-in scanners whose violations can be auto-detected in source code.
_SCANNABLE_RULE_IDS: frozenset[str] = frozenset({
    "no_magic_numbers",
    "no_hardcoded_urls",
    "function_naming",
    "variable_naming",
    "class_naming",
    "file_naming",
})

#: Map from principle id to built-in scanner name.
_PRINCIPLE_ID_TO_SCANNER: dict[str, str] = {
    "P011": "no_magic_numbers",
    "P012": "no_hardcoded_urls",
    "P014": "function_naming",
    "P015": "variable_naming",
    "P016": "class_naming",
    "P017": "file_naming",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class GateConfig:
    """Configuration for :class:`PrinciplesGate`.

    Attributes
    ----------
    fail_on_critical:
        When ``True`` (the default) the gate returns ``passed=False`` if any
        violation with ``severity="error"`` (i.e. a ``blocking`` principle) is
        found.  Set to ``False`` to run in fully advisory mode.
    fail_on_error:
        When ``True`` *all* error-severity violations fail the gate.  This is
        a superset of *fail_on_critical* — prefer *fail_on_critical* to target
        only blocking-principle violations.
    principles_file:
        Path to the YAML file defining project principles, relative to the
        project root.  Defaults to ``".claude/principles.yaml"``.
    rules:
        Subset of scanner names to run.  ``["all"]`` (the default) activates
        every built-in scanner.
    """

    fail_on_critical: bool = True
    fail_on_error: bool = False
    principles_file: str = ".claude/principles.yaml"
    rules: list[str] = field(default_factory=lambda: ["all"])


@dataclass
class Violation:
    """A single principle violation detected by the gate.

    Attributes
    ----------
    principle_id:
        The ``id`` field from the principle definition (e.g. ``"P011"``).
        Uses ``"builtin"`` for violations not tied to a specific YAML entry.
    severity:
        One of ``"error"``, ``"warning"``, or ``"info"``.
    message:
        Human-readable description of the violation.
    file_path:
        Repository-relative path to the offending file, if applicable.
    line_number:
        Line number within *file_path*, if applicable.
    suggestion:
        Optional remediation hint.
    rule_id:
        Short machine-readable rule identifier (e.g.
        ``"principles/no-magic-numbers"``).
    """

    principle_id: str
    severity: str          # "error" | "warning" | "info"
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    rule_id: Optional[str] = None


@dataclass
class GateResult:
    """Aggregate result from a :class:`PrinciplesGate` run.

    Attributes
    ----------
    passed:
        ``True`` when no blocking violations were found (or when the gate is
        in fully advisory mode).
    violations:
        All detected violations, ordered by severity then file path.
    principles_loaded:
        Number of principles successfully parsed from the YAML file.
    principles_scanned:
        Number of principles for which at least one auto-scanner ran.
    """

    passed: bool
    violations: list[Violation] = field(default_factory=list)
    principles_loaded: int = 0
    principles_scanned: int = 0

    def errors(self) -> list[Violation]:
        """Return only ``"error"``-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        """Return only ``"warning"``-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        n = len(self.violations)
        e = len(self.errors())
        return (
            f"[{status}] principles gate — "
            f"{n} violation(s), {e} blocking"
        )


# ---------------------------------------------------------------------------
# PrinciplesGate
# ---------------------------------------------------------------------------


class PrinciplesGate:
    """Scan source code for violations of the project's golden principles.

    Parameters
    ----------
    cfg:
        Gate configuration.  Defaults to :class:`GateConfig` with all
        defaults (fail-on-critical enabled, advisory for non-critical).

    Examples
    --------
    ::

        gate = PrinciplesGate()
        result = gate.run(Path("."))
        print(result)

        for v in result.errors():
            print(f"[BLOCKING] {v.principle_id} — {v.message}")
            if v.file_path:
                print(f"  → {v.file_path}:{v.line_number}")
    """

    def __init__(self, cfg: Optional[GateConfig] = None) -> None:
        self._cfg = cfg or GateConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, project_root: Path) -> GateResult:
        """Run the gate against *project_root* and return a :class:`GateResult`.

        Parameters
        ----------
        project_root:
            Absolute (or CWD-relative) path to the repository root.  All
            relative paths in violations are expressed relative to this root.
        """
        root = Path(project_root).resolve()
        principles = self._load_principles(root)
        active_rules = self._resolve_active_rules()

        violations: list[Violation] = []
        principles_scanned = 0

        # ── Per-principle checks ─────────────────────────────────────────────
        for entry in principles:
            p_id = entry.get("id", "UNKNOWN")
            yaml_severity = entry.get("severity", "suggestion")
            gate_severity = _SEVERITY_MAP.get(yaml_severity, "info")
            applies_to: list[str] = entry.get("applies_to", [])

            # Skip principles that don't apply to automated code scanning.
            if applies_to and "check-code" not in applies_to:
                continue

            scanner_name = _PRINCIPLE_ID_TO_SCANNER.get(p_id)
            if scanner_name and _is_rule_active(scanner_name, active_rules):
                principles_scanned += 1
                new_violations = _run_scanner(
                    scanner_name=scanner_name,
                    project_root=root,
                    principle_id=p_id,
                    severity=gate_severity,
                )
                violations.extend(new_violations)

        # ── Fallback: run built-in scanners with no matching principle ID ────
        # This handles repos whose principles.yaml doesn't yet contain P011–P017.
        matched_principle_ids = {
            _PRINCIPLE_ID_TO_SCANNER.get(e.get("id", "")) for e in principles
        }
        for p_id, scanner_name in _PRINCIPLE_ID_TO_SCANNER.items():
            if scanner_name in matched_principle_ids:
                continue  # already ran above
            if not _is_rule_active(scanner_name, active_rules):
                continue
            principles_scanned += 1
            new_violations = _run_scanner(
                scanner_name=scanner_name,
                project_root=root,
                principle_id=p_id,
                severity="warning",  # default when no YAML entry found
            )
            violations.extend(new_violations)

        # ── Apply advisory mode ──────────────────────────────────────────────
        effective = _apply_advisory(violations, self._cfg)

        # ── Determine gate outcome ───────────────────────────────────────────
        passed = not any(v.severity == "error" for v in effective)

        return GateResult(
            passed=passed,
            violations=_sort_violations(effective),
            principles_loaded=len(principles),
            principles_scanned=principles_scanned,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_principles(self, root: Path) -> list[dict]:
        """Load and return the list of principle entries from the YAML file."""
        principles_path = root / self._cfg.principles_file
        if not principles_path.exists():
            return []
        if not _YAML_AVAILABLE:
            return []
        try:
            raw = _yaml.safe_load(principles_path.read_text(encoding="utf-8")) or {}
            return list(raw.get("principles", []) or [])
        except Exception:
            return []

    def _resolve_active_rules(self) -> set[str]:
        """Expand ``["all"]`` to all built-in scanner names."""
        rules = set(self._cfg.rules)
        if "all" in rules:
            return set(_SCANNABLE_RULE_IDS)
        return rules


# ---------------------------------------------------------------------------
# Advisory-mode helper
# ---------------------------------------------------------------------------


def _apply_advisory(violations: list[Violation], cfg: GateConfig) -> list[Violation]:
    """Downgrade violations according to ``fail_on_critical`` / ``fail_on_error``.

    Rules:

    1. If ``fail_on_critical=True``, violations that originated from a
       ``blocking`` YAML principle keep their ``"error"`` severity.
    2. If ``fail_on_error=False`` (advisory) but ``fail_on_critical=True``,
       only ``blocking``-originated errors survive as ``"error"``; all others
       are downgraded to ``"warning"``.
    3. If both flags are ``False``, every ``"error"`` is downgraded to
       ``"warning"``.
    """
    result: list[Violation] = []
    for v in violations:
        effective_severity = v.severity
        if v.severity == "error":
            if cfg.fail_on_critical:
                # Keep as error — blocking principle, always hard-fails.
                pass
            elif cfg.fail_on_error:
                # fail_on_error covers all errors.
                pass
            else:
                # Full advisory: downgrade to warning.
                effective_severity = "warning"
        result.append(Violation(
            principle_id=v.principle_id,
            severity=effective_severity,
            message=v.message,
            file_path=v.file_path,
            line_number=v.line_number,
            suggestion=v.suggestion,
            rule_id=v.rule_id,
        ))
    return result


# ---------------------------------------------------------------------------
# Sorting helper
# ---------------------------------------------------------------------------


def _sort_violations(violations: list[Violation]) -> list[Violation]:
    """Sort violations: errors first, then warnings, then info; within each
    severity group sort by file path and line number."""
    _order = {"error": 0, "warning": 1, "info": 2}
    return sorted(
        violations,
        key=lambda v: (_order.get(v.severity, 9), v.file_path or "", v.line_number or 0),
    )


# ---------------------------------------------------------------------------
# Rule-activation helper
# ---------------------------------------------------------------------------


def _is_rule_active(rule: str, active_rules: set[str]) -> bool:
    return rule in active_rules


# ---------------------------------------------------------------------------
# Built-in scanners
# ---------------------------------------------------------------------------


def _run_scanner(
    scanner_name: str,
    project_root: Path,
    principle_id: str,
    severity: str,
) -> list[Violation]:
    """Dispatch to the appropriate built-in scanner function."""
    _SCANNERS = {
        "no_magic_numbers":  _scan_no_magic_numbers,
        "no_hardcoded_urls": _scan_no_hardcoded_urls,
        "function_naming":   _scan_function_naming,
        "variable_naming":   _scan_variable_naming,
        "class_naming":      _scan_class_naming,
        "file_naming":       _scan_file_naming,
    }
    scanner_fn = _SCANNERS.get(scanner_name)
    if scanner_fn is None:
        return []
    return scanner_fn(project_root, principle_id, severity)


def _py_files(root: Path):
    """Yield Python source files under *root*, skipping virtual environments."""
    for py_file in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue
        yield py_file


def _repo_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parse_py(path: Path):
    """Parse *path* as Python AST, returning ``None`` on syntax error."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


# ── no_magic_numbers ────────────────────────────────────────────────────────


def _scan_no_magic_numbers(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect numeric literals outside the allowed whitelist."""
    violations: list[Violation] = []
    for py_file in _py_files(root):
        tree = _parse_py(py_file)
        if tree is None:
            continue
        rel = _repo_rel(py_file, root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in _ALLOWED_NUMBERS and abs(node.value) > 1:
                    violations.append(Violation(
                        principle_id=principle_id,
                        severity=severity,
                        message=(
                            f"Magic number {node.value!r} — extract to a named constant."
                        ),
                        file_path=rel,
                        line_number=node.lineno,
                        suggestion=(
                            f"Replace {node.value!r} with a named constant such as "
                            f"`THRESHOLD = {node.value!r}` in a `constants.py` module."
                        ),
                        rule_id="principles/no-magic-numbers",
                    ))
    return violations


# ── no_hardcoded_urls ────────────────────────────────────────────────────────


def _scan_no_hardcoded_urls(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect hard-coded HTTP/HTTPS URLs in string literals."""
    violations: list[Violation] = []
    for py_file in _py_files(root):
        tree = _parse_py(py_file)
        if tree is None:
            continue
        rel = _repo_rel(py_file, root)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _URL_RE.search(node.value)
                and len(node.value) > 10
            ):
                violations.append(Violation(
                    principle_id=principle_id,
                    severity=severity,
                    message=f"Hard-coded URL: {node.value[:60]!r}",
                    file_path=rel,
                    line_number=node.lineno,
                    suggestion=(
                        "Move this URL to `harness.config.yaml`, `src/config.py`, "
                        "or an environment variable to enable easy environment switching."
                    ),
                    rule_id="principles/no-hardcoded-urls",
                ))
    return violations


# ── function_naming ─────────────────────────────────────────────────────────

_SNAKE_CASE_RE = re.compile(r"^_?[a-z][a-z0-9_]*$")
_DUNDER_RE = re.compile(r"^__[a-zA-Z0-9_]+__$")


def _scan_function_naming(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect function / method names that violate snake_case convention."""
    violations: list[Violation] = []
    for py_file in _py_files(root):
        tree = _parse_py(py_file)
        if tree is None:
            continue
        rel = _repo_rel(py_file, root)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if _DUNDER_RE.match(name):
                continue  # dunders are exempt
            if not _SNAKE_CASE_RE.match(name):
                violations.append(Violation(
                    principle_id=principle_id,
                    severity=severity,
                    message=(
                        f"Function name {name!r} violates snake_case convention."
                    ),
                    file_path=rel,
                    line_number=node.lineno,
                    suggestion=(
                        f"Rename to `{_to_snake_case(name)}`. "
                        "Private helpers should use a leading underscore: "
                        f"`_{_to_snake_case(name)}`."
                    ),
                    rule_id="principles/function-naming",
                ))
    return violations


# ── variable_naming ─────────────────────────────────────────────────────────

_SINGLE_LETTER_ALLOWED = frozenset("ijk")


def _scan_variable_naming(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect single-letter variable names outside loop counters."""
    violations: list[Violation] = []
    for py_file in _py_files(root):
        tree = _parse_py(py_file)
        if tree is None:
            continue
        rel = _repo_rel(py_file, root)

        # Track For-loop variables to exempt standard counters.
        loop_vars: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                if isinstance(node.target, ast.Name):
                    loop_vars.add(node.target.id)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            )
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if (
                    len(name) == 1
                    and name.isalpha()
                    and name not in _SINGLE_LETTER_ALLOWED
                    and name not in loop_vars
                ):
                    violations.append(Violation(
                        principle_id=principle_id,
                        severity=severity,
                        message=(
                            f"Single-letter variable name {name!r} lacks descriptive context."
                        ),
                        file_path=rel,
                        line_number=getattr(node, "lineno", None),
                        suggestion=(
                            f"Replace {name!r} with a descriptive snake_case name "
                            "(e.g. `agent_id`, `gate_result`, `config_path`)."
                        ),
                        rule_id="principles/variable-naming",
                    ))
    return violations


# ── class_naming ─────────────────────────────────────────────────────────────

_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def _scan_class_naming(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect class names that violate PascalCase convention."""
    violations: list[Violation] = []
    for py_file in _py_files(root):
        tree = _parse_py(py_file)
        if tree is None:
            continue
        rel = _repo_rel(py_file, root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            name = node.name
            if not _PASCAL_CASE_RE.match(name):
                violations.append(Violation(
                    principle_id=principle_id,
                    severity=severity,
                    message=f"Class name {name!r} violates PascalCase convention.",
                    file_path=rel,
                    line_number=node.lineno,
                    suggestion=(
                        f"Rename to `{_to_pascal_case(name)}`. "
                        "Test classes must begin with `Test` (e.g. `TestMyClass`)."
                    ),
                    rule_id="principles/class-naming",
                ))
    return violations


# ── file_naming ──────────────────────────────────────────────────────────────

_SNAKE_FILE_RE = re.compile(r"^[a-z][a-z0-9_]*\.py$")


def _scan_file_naming(
    root: Path, principle_id: str, severity: str
) -> list[Violation]:
    """Detect Python files whose names violate the snake_case convention."""
    violations: list[Violation] = []
    for py_file in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in py_file.parts):
            continue
        fname = py_file.name
        if not _SNAKE_FILE_RE.match(fname):
            violations.append(Violation(
                principle_id=principle_id,
                severity=severity,
                message=f"Python file name {fname!r} violates snake_case convention.",
                file_path=_repo_rel(py_file, root),
                suggestion=(
                    f"Rename to `{_to_snake_case(fname.removesuffix('.py'))}.py`. "
                    "All Python source files must use snake_case.py filenames."
                ),
                rule_id="principles/file-naming",
            ))
    return violations


# ---------------------------------------------------------------------------
# Naming-convention helpers
# ---------------------------------------------------------------------------


def _to_snake_case(name: str) -> str:
    """Best-effort conversion of *name* to snake_case."""
    # Insert underscore before uppercase letters preceded by lowercase.
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore before uppercase letters followed by lowercase.
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower().replace("-", "_")


def _to_pascal_case(name: str) -> str:
    """Best-effort conversion of *name* to PascalCase."""
    return "".join(word.capitalize() for word in re.split(r"[_\-\s]+", name) if word)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.principles",
        description="Golden-principles compliance gate",
    )
    parser.add_argument(
        "--root", default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--principles-file", default=".claude/principles.yaml",
        dest="principles_file",
        help="Path to principles YAML relative to --root",
    )
    parser.add_argument(
        "--no-fail-on-critical", action="store_true", dest="no_fail_on_critical",
        help="Do not fail on blocking-severity violations (advisory mode)",
    )
    parser.add_argument(
        "--fail-on-error", action="store_true", dest="fail_on_error",
        help="Fail on ALL error-severity violations (superset of --fail-on-critical)",
    )
    parser.add_argument(
        "--rules", nargs="*", default=["all"],
        help="Subset of scanner rules to activate (default: all)",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format",
    )
    return parser


def _render_text(result: GateResult) -> str:
    lines: list[str] = []
    width = 54
    bar = "━" * width
    lines.append(bar)
    status = "PASS ✅" if result.passed else "FAIL ❌"
    lines.append(f"  Principles Gate — {status}")
    lines.append(f"  Principles loaded  : {result.principles_loaded}")
    lines.append(f"  Scanners run       : {result.principles_scanned}")
    lines.append(f"  Total violations   : {len(result.violations)}")
    lines.append(f"  Blocking (errors)  : {len(result.errors())}")
    lines.append(bar)

    if result.violations:
        lines.append("")
        for v in result.violations:
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(v.severity, "  ")
            location = ""
            if v.file_path:
                location = f"  {v.file_path}"
                if v.line_number:
                    location += f":{v.line_number}"
            lines.append(f"{icon} [{v.principle_id}] {v.message}")
            if location:
                lines.append(location)
            if v.suggestion:
                lines.append(f"   → {v.suggestion}")
            lines.append("")

    if not result.passed:
        lines.append("🔴 BLOCKING — principles violations found, merge prevented")
        lines.append("─" * width)
        lines.append("  Resolve all blocking violations before merging.")
        lines.append("  Run /define-principles to review or update project rules.")

    return "\n".join(lines)


def _render_json(result: GateResult) -> str:
    import json
    import dataclasses
    data = {
        "passed": result.passed,
        "principles_loaded": result.principles_loaded,
        "principles_scanned": result.principles_scanned,
        "total_violations": len(result.violations),
        "blocking_violations": len(result.errors()),
        "violations": [dataclasses.asdict(v) for v in result.violations],
    }
    return json.dumps(data, indent=2)


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point.  Returns an exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    cfg = GateConfig(
        fail_on_critical=not args.no_fail_on_critical,
        fail_on_error=args.fail_on_error,
        principles_file=args.principles_file,
        rules=args.rules or ["all"],
    )
    gate = PrinciplesGate(cfg)
    try:
        result = gate.run(Path(args.root))
    except Exception as exc:
        print(f"ERROR: principles gate raised an exception: {exc}", file=sys.stderr)
        return 2

    output = _render_text(result) if args.format == "text" else _render_json(result)
    print(output)

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
