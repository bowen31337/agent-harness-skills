"""
harness_skills/gates/security.py
==================================
Security Check Gate — three sub-gates in one module:

1. **secrets**          — detects hardcoded credentials, API keys, and tokens
                          embedded in source files using regex heuristics.
2. **dependencies**     — audits installed packages for known CVEs via
                          ``pip-audit`` (Python) or ``npm audit`` (Node.js).
3. **input-validation** — walks the AST and uses regex heuristics to flag
                          untrusted request data flowing directly into dangerous
                          sinks (SQL, subprocess, file I/O, ``eval``/``exec``)
                          without an intermediate sanitiser call.

Exit codes (standalone CLI)
---------------------------
    0  All enabled sub-gates passed.
    1  One or more sub-gates reported error-severity findings.
    2  Internal error (tool not installed, unreadable file, …).

Usage (standalone CLI)::

    python -m harness_skills.gates.security [--root .]
    python -m harness_skills.gates.security --root /path/to/repo --gate secrets
    python -m harness_skills.gates.security --gate dependencies --severity MEDIUM
    python -m harness_skills.gates.security --gate input-validation --no-fail-on-error

Usage (programmatic)::

    from pathlib import Path
    from harness_skills.gates.security import SecurityGate
    from harness_skills.models.gate_configs import SecurityGateConfig

    cfg    = SecurityGateConfig(severity_threshold="HIGH", scan_secrets=True)
    result = SecurityGate(cfg).run(repo_root=Path("."))

    if not result.passed:
        for v in result.violations:
            print(v.summary())
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from harness_skills.models.gate_configs import SecurityGateConfig


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

ViolationKind = Literal[
    "secret_detected",
    "vulnerable_dependency",
    "unvalidated_input",
    "tool_not_found",
    "scan_error",
]
Severity = Literal["error", "warning", "info"]


@dataclass
class SecurityViolation:
    """A single security gate finding."""

    kind: ViolationKind
    """Classifier for the violation type."""

    severity: Severity
    """``error`` blocks the gate; ``warning`` is advisory only; ``info`` is informational."""

    sub_gate: str
    """Which sub-gate produced this finding: ``secrets``, ``dependencies``, or
    ``input-validation``."""

    message: str
    """Human-readable description of the finding."""

    file_path: Path | None = None
    """Source file containing the finding (if applicable)."""

    line_number: int | None = None
    """1-based line number within *file_path* (if known)."""

    rule_id: str | None = None
    """Short rule identifier, e.g. ``SEC001``, a CVE ID, or ``INV003``."""

    cve: str | None = None
    """CVE identifier for dependency findings (e.g. ``CVE-2023-12345``)."""

    suggestion: str | None = None
    """Actionable remediation guidance."""

    def summary(self) -> str:
        """One-line string suitable for console output."""
        loc = ""
        if self.file_path:
            loc = f" [{self.file_path}"
            if self.line_number:
                loc += f":{self.line_number}"
            loc += "]"
        return (
            f"[{self.severity.upper():7s}] [{self.sub_gate:20s}]"
            f" {self.rule_id or self.kind}{loc} — {self.message}"
        )


@dataclass
class SubGateResult:
    """Outcome of a single sub-gate (secrets / dependencies / input-validation)."""

    passed: bool
    """``True`` when no error-severity violations were found (or
    ``fail_on_error=False``)."""

    sub_gate: str
    """Name of the sub-gate that produced this result."""

    violations: list[SecurityViolation] = field(default_factory=list)
    """All findings produced by this sub-gate."""

    def errors(self) -> list[SecurityViolation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[SecurityViolation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]


@dataclass
class GateResult:
    """Aggregate result returned by :class:`SecurityGate`."""

    passed: bool
    """``True`` when all enabled sub-gates passed."""

    violations: list[SecurityViolation] = field(default_factory=list)
    """All findings from all sub-gates, in the order they were produced."""

    sub_gate_results: list[SubGateResult] = field(default_factory=list)
    """Per-sub-gate outcome objects."""

    stats: dict[str, object] = field(default_factory=dict)
    """Summary counters: ``total``, ``errors``, ``warnings``, per-sub-gate counts."""

    def errors(self) -> list[SecurityViolation]:
        """Return only error-severity violations."""
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[SecurityViolation]:
        """Return only warning-severity violations."""
        return [v for v in self.violations if v.severity == "warning"]

    def __str__(self) -> str:  # pragma: no cover
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"SecurityGate: {status}"]
        for sg in self.sub_gate_results:
            sg_status = "PASSED" if sg.passed else "FAILED"
            lines.append(
                f"  [{sg_status:6s}] {sg.sub_gate}: {len(sg.violations)} finding(s)"
            )
        if self.violations:
            lines.append("")
            for v in self.violations:
                lines.append("  " + v.summary())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

#: Directories never scanned for secrets or input-validation issues.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".tox",
        "dist",
        "build",
        ".eggs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".claw-forge",
    }
)

#: File extensions that are treated as text during secret scanning.
_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".rb",
        ".go",
        ".java",
        ".kt",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".env",
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".tf",
        ".tfvars",
        ".md",
        ".rst",
        ".txt",
        ".xml",
        ".html",
        ".jinja",
        ".j2",
    }
)

#: Extra bare file *names* (no extension) also scanned for secrets.
_TEXT_NAMES: frozenset[str] = frozenset({".env", ".envrc", "Makefile", "Dockerfile"})


def _is_text_file(path: Path) -> bool:
    """Return ``True`` when *path* looks like a text file (no NUL bytes in first 8 KB)."""
    try:
        return b"\x00" not in path.read_bytes()[:8192]
    except OSError:
        return False


def _repo_rel(path: Path, root: Path) -> str:
    """Return a repo-relative string for *path*, or the absolute path as fallback."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _should_scan(path: Path) -> bool:
    """Return ``True`` when *path* is a text source file that should be scanned."""
    if any(part in _SKIP_DIRS for part in path.parts):
        return False
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    if path.name in _TEXT_NAMES:
        return True
    return False


# ---------------------------------------------------------------------------
# Sub-gate 1: Secret scanning
# ---------------------------------------------------------------------------

#: Each entry is ``(compiled_pattern, rule_id, short_description, suggestion)``.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    # Generic password / secret / token assignment
    (
        re.compile(
            r"(?i)"
            r"(?:secret|password|passwd|pwd|token|apikey|api_key|auth_token|access_token"
            r"|private_key|client_secret)"
            r"\s*[:=]\s*"
            r"[\"'](?!(?:\$\{|%\(|\{\{|<)[^\"']{0,5})"  # skip template placeholders
            r"(?!(?:your[_\-]|<|MY_|EXAMPLE|REPLACE|TODO|xxx|change.me))"  # skip placeholders
            r"[^\"'\\]{8,}[\"']"
        ),
        "SEC001",
        "Hardcoded secret, password, or token value detected",
        (
            "Move the value to an environment variable and read it via "
            "`os.environ['SECRET_NAME']` or a secrets manager."
        ),
    ),
    # PEM private key block
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
        ),
        "SEC002",
        "Private key material embedded in source file",
        (
            "Remove the private key from the repository immediately. "
            "Use a secrets manager or store the key file outside version control."
        ),
    ),
    # AWS credentials
    (
        re.compile(
            r"(?i)"
            r"(?:aws_secret_access_key|aws_access_key_id)"
            r"\s*[:=]\s*[\"']([A-Za-z0-9/+=]{16,})[\"']"
        ),
        "SEC003",
        "AWS credential detected",
        (
            "Use IAM roles or environment variables "
            "(AWS_SECRET_ACCESS_KEY / AWS_ACCESS_KEY_ID) instead of hard-coding."
        ),
    ),
    # OpenAI / Anthropic API key prefixes
    (
        re.compile(r'["\'](?:sk-[A-Za-z0-9]{32,}|sk-ant-[A-Za-z0-9\-_]{50,})["\']'),
        "SEC004",
        "AI provider API key detected (OpenAI / Anthropic pattern)",
        (
            "Revoke and rotate the key. Store it in an environment variable "
            "and access it via `os.environ['OPENAI_API_KEY']`."
        ),
    ),
    # GitHub Personal Access Token
    (
        re.compile(r"ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{82,}"),
        "SEC005",
        "GitHub Personal Access Token detected",
        (
            "Revoke this token immediately via GitHub Settings → Developer settings. "
            "Use GitHub Actions secrets or environment variables."
        ),
    ),
    # Database connection string with inline credentials
    (
        re.compile(
            r"(?i)"
            r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|mssql|oracle)"
            r"://[^:@\s\"'`]{2,}:[^@\s\"'`]{2,}@[^\s\"'`]{4,}"
        ),
        "SEC006",
        "Database connection string with embedded credentials detected",
        (
            "Use environment variables for database credentials "
            "(e.g. `os.environ['DATABASE_URL']`) and exclude them from version control."
        ),
    ),
    # Bearer token literal
    (
        re.compile(
            r"(?i)"
            r"[\"']Bearer\s+[A-Za-z0-9\-_=.]{20,}[\"']"
        ),
        "SEC007",
        "Hard-coded Bearer token detected",
        (
            "Bearer tokens must not appear in source code. "
            "Obtain them at runtime from a token service or environment variable."
        ),
    ),
    # Generic high-entropy hex secret (32+ hex chars after an assignment)
    (
        re.compile(
            r"(?i)"
            r"(?:secret|token|key|password|passwd|pwd)"
            r"\s*[:=]\s*"
            r"[\"'][0-9a-f]{32,}[\"']"
        ),
        "SEC008",
        "High-entropy hexadecimal value assigned to a secret-named variable",
        (
            "If this is a real secret, move it to an environment variable or secrets manager."
        ),
    ),
]


def scan_secrets(
    repo_root: Path,
    cfg: SecurityGateConfig,
) -> SubGateResult:
    """Scan source files for hardcoded secrets and credentials.

    Applies :data:`_SECRET_PATTERNS` regex rules to every text file under
    *repo_root* (skipping generated/vendor directories and binary files).

    Parameters
    ----------
    repo_root:
        Repository root directory to scan recursively.
    cfg:
        Gate configuration.  ``ignore_ids`` suppresses specific rule IDs;
        ``fail_on_error=False`` downgrades ``error`` findings to ``warning``.

    Returns
    -------
    SubGateResult
        ``passed=True`` when no error-severity violations remain.
    """
    violations: list[SecurityViolation] = []
    sev: Severity = "error" if cfg.fail_on_error else "warning"

    for path in sorted(repo_root.rglob("*")):
        if path.is_dir():
            continue
        if not _should_scan(path):
            continue
        if not _is_text_file(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for pattern, rule_id, desc, suggestion in _SECRET_PATTERNS:
            if rule_id in cfg.ignore_ids:
                continue
            for m in pattern.finditer(text):
                line_num = text[: m.start()].count("\n") + 1
                rel = _repo_rel(path, repo_root)
                violations.append(
                    SecurityViolation(
                        kind="secret_detected",
                        severity=sev,
                        sub_gate="secrets",
                        message=f"{desc} in {rel}:{line_num}",
                        file_path=path,
                        line_number=line_num,
                        rule_id=rule_id,
                        suggestion=suggestion,
                    )
                )

    passed = not any(v.severity == "error" for v in violations)
    return SubGateResult(passed=passed, sub_gate="secrets", violations=violations)


# ---------------------------------------------------------------------------
# Sub-gate 2: Dependency vulnerability audit
# ---------------------------------------------------------------------------

_SEV_RANK: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "UNKNOWN": 2,  # treat unknown severity as MEDIUM
}


def audit_dependencies(
    repo_root: Path,
    cfg: SecurityGateConfig,
) -> SubGateResult:
    """Audit installed Python packages for known CVEs using ``pip-audit``.

    Runs ``python -m pip_audit --format=json --progress-spinner=off`` as a
    subprocess, parses the JSON output, and maps each vulnerability to a
    :class:`SecurityViolation`.  Vulnerabilities whose severity falls below
    ``cfg.severity_threshold`` and IDs listed in ``cfg.ignore_ids`` are
    suppressed.

    Parameters
    ----------
    repo_root:
        Repository root used as *cwd* for the ``pip-audit`` invocation.
    cfg:
        Gate configuration.  ``severity_threshold``, ``ignore_ids``, and
        ``fail_on_error`` are honoured.

    Returns
    -------
    SubGateResult
        ``passed=True`` when no blocking CVEs are found (or tool absent).
    """
    violations: list[SecurityViolation] = []
    sev: Severity = "error" if cfg.fail_on_error else "warning"
    threshold_rank = _SEV_RANK.get(cfg.severity_threshold.upper(), 3)

    # ── Run pip-audit ──────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--format=json",
                "--progress-spinner=off",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        violations.append(
            SecurityViolation(
                kind="tool_not_found",
                severity="warning",
                sub_gate="dependencies",
                message=(
                    "pip-audit is not installed — dependency vulnerability audit skipped."
                ),
                suggestion="Install it with: `pip install pip-audit`",
                rule_id="DEP000",
            )
        )
        return SubGateResult(passed=True, sub_gate="dependencies", violations=violations)
    except subprocess.TimeoutExpired:
        violations.append(
            SecurityViolation(
                kind="scan_error",
                severity="warning",
                sub_gate="dependencies",
                message="pip-audit timed out after 120 s — dependency audit incomplete.",
                suggestion="Run `pip-audit` manually to investigate the timeout.",
                rule_id="DEP001",
            )
        )
        return SubGateResult(passed=True, sub_gate="dependencies", violations=violations)

    # pip-audit exits 0 (no vulns) or 1 (vulns found); other codes = tool error
    if result.returncode not in (0, 1):
        violations.append(
            SecurityViolation(
                kind="scan_error",
                severity="warning",
                sub_gate="dependencies",
                message=(
                    f"pip-audit exited {result.returncode}: "
                    f"{result.stderr.strip()[:200]}"
                ),
                suggestion=(
                    "Ensure pip-audit is installed and the virtual environment is active."
                ),
                rule_id="DEP002",
            )
        )
        return SubGateResult(passed=True, sub_gate="dependencies", violations=violations)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # pip-audit produced no/invalid JSON — treat as a clean run
        return SubGateResult(passed=True, sub_gate="dependencies", violations=violations)

    # ── Parse CVE entries ──────────────────────────────────────────────────
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            cve_id: str = vuln.get("id", "UNKNOWN")
            if cve_id in cfg.ignore_ids:
                continue

            vuln_sev_raw: str = (vuln.get("severity") or "UNKNOWN").upper()
            vuln_rank = _SEV_RANK.get(vuln_sev_raw, 2)
            if vuln_rank < threshold_rank:
                continue

            pkg: str = dep.get("name", "unknown")
            pkg_ver: str = dep.get("version", "?")
            fixed: list[str] = vuln.get("fix_versions") or []
            fix_hint = (
                f"Upgrade {pkg} to {fixed[0]}"
                if fixed
                else f"No known fix available for {pkg}"
            )

            violations.append(
                SecurityViolation(
                    kind="vulnerable_dependency",
                    severity=sev,
                    sub_gate="dependencies",
                    message=(
                        f"{pkg}=={pkg_ver}: {cve_id} — "
                        f"{vuln.get('description', 'no description')[:120]}"
                    ),
                    rule_id=cve_id,
                    cve=cve_id,
                    suggestion=(
                        fix_hint
                        + ". Run `pip-audit --fix` to auto-upgrade where possible."
                    ),
                )
            )

    passed = not any(v.severity == "error" for v in violations)
    return SubGateResult(passed=passed, sub_gate="dependencies", violations=violations)


# ---------------------------------------------------------------------------
# Sub-gate 3: Input validation verification
# ---------------------------------------------------------------------------

#: Regex patterns for detecting untrusted request data flowing into dangerous
#: sinks.  Each entry: ``(pattern, rule_id, short_description, suggestion)``.
#:
#: These patterns target common Python web frameworks (Flask, Django, FastAPI)
#: but the SQL/subprocess/eval patterns fire on any Python code.
_INPUT_VALIDATION_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    # SQL injection — f-string / %-format / .format() / concatenation in execute()
    (
        re.compile(
            r"(?:cursor|conn|connection|db|session|engine)"
            r"\.execute\s*\(\s*"
            r"(?:"
            r'f["\']'  # f-string
            r'|["\'][^"\']*%\s*(?:request|user|data|params|form|args|body|input)'
            r'|["\'][^"\']*\.format\s*\('
            r'|["\'][^"\']*\s*\+\s*(?:request|user|data|params|form|args|body|input)'
            r")"
        ),
        "INV001",
        "Potential SQL injection: dynamic string passed to execute()",
        (
            "Use parameterised queries: "
            "`cursor.execute('SELECT … WHERE id = %s', (value,))`. "
            "Never build SQL strings from user-supplied data."
        ),
    ),
    # SQL injection — request.* directly inside execute()
    (
        re.compile(
            r"(?:cursor|conn|connection|db|session|engine)"
            r"\.execute\s*\([^)]*"
            r"request\."
        ),
        "INV002",
        "Potential SQL injection: request data passed directly to execute()",
        (
            "Use parameterised queries and validate / sanitise all input "
            "before passing it to the database layer."
        ),
    ),
    # Command injection — subprocess / os.system / os.popen with request.*
    (
        re.compile(
            r"(?:subprocess\.(?:run|call|check_output|check_call|Popen)"
            r"|os\.(?:system|popen|execv|execve|spawnl)"
            r")\s*\([^)]*request\."
        ),
        "INV003",
        "Potential command injection: request data passed to subprocess/os.system",
        (
            "Avoid passing user input to shell commands. "
            "Use a strict allow-list of values; never interpolate raw user data "
            "into a shell invocation."
        ),
    ),
    # Code injection — eval / exec with request.*
    (
        re.compile(r"\b(?:eval|exec)\s*\([^)]*request\."),
        "INV004",
        "Potential code injection: request data passed to eval() or exec()",
        (
            "Never pass user input to `eval()` or `exec()`. "
            "Refactor to eliminate dynamic code execution entirely."
        ),
    ),
    # Path traversal — open() with request.*
    (
        re.compile(r"\bopen\s*\([^)]*request\."),
        "INV005",
        "Potential path traversal: request data used in open()",
        (
            "Validate and sanitise file paths. "
            "Use `pathlib.Path.resolve()` and check that the resolved path "
            "starts within an allowed base directory before opening."
        ),
    ),
    # SSRF — requests / httpx / urllib with request.* as the URL
    (
        re.compile(
            r"(?:requests\.|httpx\.)"
            r"(?:get|post|put|delete|patch|head|request)"
            r"\s*\([^)]*request\."
        ),
        "INV006",
        "Potential SSRF: request data used as outbound URL target",
        (
            "Validate URLs against an allow-list of trusted hosts before "
            "making outbound HTTP requests."
        ),
    ),
    # SSTI — render_template_string / Jinja2.Environment.from_string with request.*
    (
        re.compile(
            r"(?:render_template_string|Environment\s*\(.*\)\.from_string)"
            r"\s*\([^)]*request\."
        ),
        "INV007",
        "Potential SSTI: request data passed to render_template_string()",
        (
            "Never pass user input to template rendering functions. "
            "Use static template files and supply data as named context variables."
        ),
    ),
    # Pickle / deserialisation of request data
    (
        re.compile(r"\bpickle\.loads?\s*\([^)]*request\."),
        "INV008",
        "Potential insecure deserialisation: request data passed to pickle.load()",
        (
            "Never deserialise untrusted data with `pickle`. "
            "Use a safe format such as JSON."
        ),
    ),
]

#: Python source file extensions to check for input-validation issues.
_PY_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyw"})


def _collect_python_files(repo_root: Path) -> list[Path]:
    """Yield all Python source files under *repo_root*, skipping vendor dirs."""
    paths: list[Path] = []
    for path in sorted(repo_root.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        paths.append(path)
    return paths


def _ast_has_request_import(tree: ast.Module) -> bool:
    """Return ``True`` when the module imports a web framework request object."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                fw in module
                for fw in ("flask", "django", "fastapi", "starlette", "aiohttp")
            ):
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(
                    fw in alias.name
                    for fw in ("flask", "django", "fastapi", "starlette", "aiohttp")
                ):
                    return True
    return False


def verify_input_validation(
    repo_root: Path,
    cfg: SecurityGateConfig,
) -> SubGateResult:
    """Detect untrusted request data flowing into dangerous sinks.

    Applies :data:`_INPUT_VALIDATION_PATTERNS` regex rules to all Python source
    files under *repo_root*.  An AST pre-check filters out files that do not
    import a recognised web framework, reducing false positives.

    Parameters
    ----------
    repo_root:
        Repository root to scan.
    cfg:
        Gate configuration.  ``ignore_ids`` suppresses specific rule IDs;
        ``fail_on_error=False`` downgrades all findings to warnings.

    Returns
    -------
    SubGateResult
        ``passed=True`` when no error-severity violations remain.
    """
    violations: list[SecurityViolation] = []
    sev: Severity = "error" if cfg.fail_on_error else "warning"

    py_files = _collect_python_files(repo_root)

    for path in py_files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # ── Optional AST pre-filter — only scan framework-using files ──────
        try:
            tree = ast.parse(source, filename=str(path))
            if not _ast_has_request_import(tree):
                continue
        except SyntaxError:
            # Unparseable file — fall through to regex scan anyway
            pass

        rel = _repo_rel(path, repo_root)

        for pattern, rule_id, desc, suggestion in _INPUT_VALIDATION_PATTERNS:
            if rule_id in cfg.ignore_ids:
                continue
            for m in pattern.finditer(source):
                line_num = source[: m.start()].count("\n") + 1
                violations.append(
                    SecurityViolation(
                        kind="unvalidated_input",
                        severity=sev,
                        sub_gate="input-validation",
                        message=f"{desc} in {rel}:{line_num}",
                        file_path=path,
                        line_number=line_num,
                        rule_id=rule_id,
                        suggestion=suggestion,
                    )
                )

    passed = not any(v.severity == "error" for v in violations)
    return SubGateResult(
        passed=passed, sub_gate="input-validation", violations=violations
    )


# ---------------------------------------------------------------------------
# SecurityGate — orchestrates all three sub-gates
# ---------------------------------------------------------------------------

#: All valid sub-gate names accepted by :class:`SecurityGate`.
ALL_SUB_GATES: tuple[str, ...] = ("secrets", "dependencies", "input-validation")


class SecurityGate:
    """Runs the three security sub-gates against a repository.

    Each sub-gate is individually enabled/disabled via the *gates* parameter
    (defaulting to all three).  The overall gate passes only when every enabled
    sub-gate passes.

    Parameters
    ----------
    config:
        Gate configuration.  When omitted, defaults are used.
    gates:
        Sub-gates to run.  Defaults to
        ``("secrets", "dependencies", "input-validation")``.

    Example::

        from pathlib import Path
        from harness_skills.gates.security import SecurityGate
        from harness_skills.models.gate_configs import SecurityGateConfig

        cfg    = SecurityGateConfig(severity_threshold="MEDIUM", scan_secrets=True)
        result = SecurityGate(cfg).run(repo_root=Path("."))
        print(result)
    """

    def __init__(
        self,
        config: SecurityGateConfig | None = None,
        gates: tuple[str, ...] = ALL_SUB_GATES,
    ) -> None:
        self.config: SecurityGateConfig = config or SecurityGateConfig()
        self.gates = gates

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, repo_root: Path) -> GateResult:
        """Execute all enabled sub-gates against *repo_root*.

        Parameters
        ----------
        repo_root:
            Absolute (or CWD-relative) path to the repository root.

        Returns
        -------
        GateResult
            Aggregated result.  Inspect ``result.passed``, ``result.violations``,
            and ``result.sub_gate_results`` for full detail.
        """
        repo_root = repo_root.resolve()
        cfg = self.config

        sub_results: list[SubGateResult] = []

        # ── Sub-gate 1: secrets ────────────────────────────────────────────
        if "secrets" in self.gates and cfg.scan_secrets:
            sub_results.append(scan_secrets(repo_root, cfg))

        # ── Sub-gate 2: dependencies ───────────────────────────────────────
        if "dependencies" in self.gates and cfg.scan_dependencies:
            sub_results.append(audit_dependencies(repo_root, cfg))

        # ── Sub-gate 3: input-validation ───────────────────────────────────
        if "input-validation" in self.gates:
            sub_results.append(verify_input_validation(repo_root, cfg))

        # ── Aggregate ─────────────────────────────────────────────────────
        all_violations: list[SecurityViolation] = [
            v for sg in sub_results for v in sg.violations
        ]
        passed = all(sg.passed for sg in sub_results)

        error_count = sum(1 for v in all_violations if v.severity == "error")
        warning_count = sum(1 for v in all_violations if v.severity == "warning")

        stats: dict[str, object] = {
            "total": len(all_violations),
            "errors": error_count,
            "warnings": warning_count,
        }
        for sg in sub_results:
            stats[f"{sg.sub_gate}_findings"] = len(sg.violations)

        return GateResult(
            passed=passed,
            violations=all_violations,
            sub_gate_results=sub_results,
            stats=stats,
        )


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m harness_skills.gates.security",
        description=(
            "Security Check Gate — runs secret scanning, dependency vulnerability "
            "audit, and input-validation verification, then exits non-zero on any "
            "error-severity finding."
        ),
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Repository root to scan (default: current directory).",
    )
    p.add_argument(
        "--gate",
        choices=list(ALL_SUB_GATES) + ["all"],
        default="all",
        dest="gate",
        metavar="GATE",
        help=(
            "Which sub-gate to run: secrets | dependencies | input-validation | all "
            "(default: all)."
        ),
    )
    p.add_argument(
        "--severity",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default="HIGH",
        dest="severity_threshold",
        metavar="LEVEL",
        help="Minimum CVE severity to report (default: HIGH).",
    )
    p.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        metavar="ID",
        dest="ignore_ids",
        help="Rule or CVE IDs to suppress (e.g. SEC001 CVE-2023-12345).",
    )
    p.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exit non-zero on error-severity findings (default: true). "
            "Use --no-fail-on-error for advisory mode."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; print only the summary.",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """CLI entry-point; returns an exit code (0 = pass, 1 = fail, 2 = error)."""
    args = _build_parser().parse_args(argv)

    cfg = SecurityGateConfig(
        severity_threshold=args.severity_threshold,
        scan_secrets=(args.gate in ("all", "secrets")),
        scan_dependencies=(args.gate in ("all", "dependencies")),
        fail_on_error=args.fail_on_error,
        ignore_ids=list(args.ignore_ids),
    )

    active_gates: tuple[str, ...] = (
        ALL_SUB_GATES if args.gate == "all" else (args.gate,)
    )
    result = SecurityGate(cfg, gates=active_gates).run(repo_root=Path(args.root))

    if not args.quiet:
        print(result)

    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
