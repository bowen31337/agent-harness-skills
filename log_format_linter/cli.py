"""
log-lint  — CLI entry point for the log_format_linter.

Sub-commands
------------
check <path> [options]
    Scan Python / TypeScript / Go source files under *path* (or a single file)
    for log statements that violate the structured-log convention.  Exits 0 when
    no violations are found; exits 1 when violations are present.

rules <framework> [options]
    Print the generated linter rules and good/bad code examples for the given
    logging framework.

detect <path> [options]
    Auto-detect the logging framework used in a codebase.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checker import check_directory, check_file
from .detector import detect_framework
from .generator import generate_rules
from .models import (
    LogFramework,
    LogLinterConfig,
    LogViolation,
    ViolationSeverity,
)

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_RESET = "[0m"
_RED = "[31m"
_YELLOW = "[33m"
_CYAN = "[36m"
_BOLD = "[1m"
_DIM = "[2m"


def _use_colour(output_format: str) -> bool:
    return output_format == "text" and sys.stderr.isatty()


def _colour_severity(severity: str, use_colour: bool) -> str:
    if not use_colour:
        return severity
    mapping = {
        "error": f"{_RED}{_BOLD}error{_RESET}",
        "warning": f"{_YELLOW}warning{_RESET}",
        "info": f"{_CYAN}info{_RESET}",
    }
    return mapping.get(severity.lower(), severity)


# ---------------------------------------------------------------------------
# check sub-command
# ---------------------------------------------------------------------------


def _run_check(args: argparse.Namespace) -> int:
    path = Path(args.path)

    fields: list[str] = args.fields or ["domain", "trace_id"]
    severity_str: str = args.severity or "error"
    try:
        severity = ViolationSeverity(severity_str.lower())
    except ValueError:
        print(
            f"log-lint: invalid --severity value {severity_str!r}. "
            f"Choose from: error, warning, info",
            file=sys.stderr,
        )
        return 2

    ignore_patterns: list[str] = args.ignore or []
    framework_override: LogFramework | None = None
    if args.framework:
        try:
            framework_override = LogFramework(args.framework.lower())
        except ValueError:
            valid = [f.value for f in LogFramework]
            print(
                f"log-lint: unknown framework {args.framework!r}. "
                f"Valid options: {', '.join(valid)}",
                file=sys.stderr,
            )
            return 2

    config = LogLinterConfig(
        required_fields=fields,
        severity=severity,
        ignore_patterns=ignore_patterns,
        framework=framework_override,
    )

    if path.is_dir():
        violations: list[LogViolation] = check_directory(path, config=config)
    elif path.is_file():
        violations = check_file(path, config=config)
    else:
        print(f"log-lint: path not found: {path}", file=sys.stderr)
        return 2

    output_format: str = args.output or "text"
    use_col = _use_colour(output_format)

    if output_format == "json":
        result = {
            "summary": {
                "path": str(path),
                "total_violations": len(violations),
                "required_fields": fields,
                "severity": severity.value,
            },
            "violations": [
                {
                    "file": str(v.file),
                    "line": v.line,
                    "column": v.column,
                    "severity": v.severity.value,
                    "rule": v.rule,
                    "message": v.message,
                    "snippet": v.snippet,
                }
                for v in violations
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        for v in violations:
            sev = _colour_severity(v.severity.value, use_col)
            file_part = f"{_BOLD}{v.file}{_RESET}" if use_col else str(v.file)
            print(f"{file_part}:{v.line}:{v.column}: [{sev}] {v.message}")
            if v.snippet:
                snippet_prefix = "  > " if not use_col else f"  {_DIM}>{_RESET} "
                print(f"{snippet_prefix}{v.snippet.strip()}")

        if violations:
            count = len(violations)
            noun = "violation" if count == 1 else "violations"
            summary = f"\n{count} {noun} found."
            if use_col:
                summary = f"{_RED}{_BOLD}{summary}{_RESET}"
            print(summary, file=sys.stderr)
        else:
            ok_msg = "No structured-log violations found."
            if use_col:
                ok_msg = f"[32m{ok_msg}{_RESET}"
            print(ok_msg, file=sys.stderr)

    return 1 if violations else 0


# ---------------------------------------------------------------------------
# rules sub-command
# ---------------------------------------------------------------------------


def _run_rules(args: argparse.Namespace) -> int:
    framework_name: str = args.framework
    try:
        framework = LogFramework(framework_name.lower())
    except ValueError:
        valid = [f.value for f in LogFramework if f != LogFramework.UNKNOWN]
        print(
            f"log-lint: unknown framework {framework_name!r}.\n"
            f"Valid options: {', '.join(valid)}",
            file=sys.stderr,
        )
        return 2

    fields: list[str] = args.fields or ["domain", "trace_id"]
    config = LogLinterConfig(required_fields=fields)
    result = generate_rules(framework, config=config)

    output_format: str = args.output or "text"
    if output_format == "json":
        print(
            json.dumps(
                {
                    "framework": result.framework.value,
                    "language": result.language.value,
                    "description": result.description,
                    "rules": result.rules,
                    "examples": result.examples,
                },
                indent=2,
            )
        )
    else:
        use_col = sys.stdout.isatty()
        bold = _BOLD if use_col else ""
        reset = _RESET if use_col else ""
        dim = _DIM if use_col else ""

        print(f"\n{bold}Log-Lint Rules  \u2014  {framework.value}{reset}")
        print(f"{dim}{'─' * 60}{reset}")
        print(f"\n{bold}Language:{reset}     {result.language.value}")
        print(f"{bold}Framework:{reset}    {framework.value}")
        print(f"\n{bold}Description:{reset}")
        print(f"  {result.description}")

        if result.rules:
            print(f"\n{bold}Check Strategy:{reset}  {result.rules.get('check_strategy', 'n/a')}")
            patterns = result.rules.get("patterns", {})
            if patterns:
                print(f"\n{bold}Detection Patterns:{reset}")
                for key, val in patterns.items():
                    if isinstance(val, list):
                        val_str = ", ".join(repr(v) for v in val)
                    else:
                        val_str = repr(val)
                    print(f"  {key}: {val_str}")

        good = [e for e in result.examples if e["type"] == "good"]
        bad = [e for e in result.examples if e["type"] == "bad"]

        if good:
            print(f"\n{bold}\u2705 Compliant examples:{reset}")
            for ex in good:
                print(f"  {ex['code']}")

        if bad:
            print(f"\n{bold}\u274c Non-compliant examples:{reset}")
            for ex in bad:
                print(f"  {ex['code']}")

        print()

    return 0


# ---------------------------------------------------------------------------
# detect sub-command
# ---------------------------------------------------------------------------


def _run_detect(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"log-lint: path not found: {path}", file=sys.stderr)
        return 2

    framework = detect_framework(path)
    output_format: str = args.output or "text"

    if output_format == "json":
        print(json.dumps({"framework": framework.value}))
    else:
        print(f"Detected framework: {framework.value}")

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="log-lint",
        description=(
            "Lint source files to ensure every log statement carries the "
            "required structured-log fields (domain, trace_id, ...)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # check
    check_p = sub.add_parser("check", help="Scan source files for structured-log violations.")
    check_p.add_argument("path", help="File or directory to scan.")
    check_p.add_argument("--fields", nargs="+", metavar="FIELD",
                         help="Required fields (default: domain trace_id).")
    check_p.add_argument("--severity", choices=["error", "warning", "info"], default="error")
    check_p.add_argument("--framework", metavar="FRAMEWORK",
                         help="Override auto-detected logging framework.")
    check_p.add_argument("--ignore", nargs="+", metavar="PATTERN",
                         help="Glob patterns to skip.")
    check_p.add_argument("--output", choices=["text", "json"], default="text")

    # rules
    rules_p = sub.add_parser("rules", help="Print linter rules and examples for a framework.")
    rules_p.add_argument("framework", help="Logging framework (e.g. python_logging, structlog).")
    rules_p.add_argument("--fields", nargs="+", metavar="FIELD")
    rules_p.add_argument("--output", choices=["text", "json"], default="text")

    # detect
    detect_p = sub.add_parser("detect", help="Auto-detect logging framework in a codebase.")
    detect_p.add_argument("path", help="File or directory to scan.")
    detect_p.add_argument("--output", choices=["text", "json"], default="text")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code: 0=clean, 1=violations, 2=error."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "check": _run_check,
        "rules": _run_rules,
        "detect": _run_detect,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
