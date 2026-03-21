"""
Rule generator for log_format_linter.

:func:`generate_rules` returns a :class:`GeneratorResult` that describes:

* The regex / AST selectors the checker uses to find log calls.
* The field-presence checks applied to each call.
* Good and bad usage examples for developer reference.
* Framework-specific config snippets (e.g. ESLint rules) where applicable.

The generated rules are consumed by :mod:`.checker` but are also useful as
documentation that can be embedded in CI output or developer guides.
"""

from __future__ import annotations

from .models import (
    GeneratorResult,
    Language,
    LogFramework,
    LogLinterConfig,
)

# ---------------------------------------------------------------------------
# Language lookup
# ---------------------------------------------------------------------------

_LANGUAGE_MAP: dict[LogFramework, Language] = {
    LogFramework.PYTHON_LOGGING: Language.PYTHON,
    LogFramework.STRUCTLOG: Language.PYTHON,
    LogFramework.LOGURU: Language.PYTHON,
    LogFramework.WINSTON: Language.TYPESCRIPT,
    LogFramework.PINO: Language.TYPESCRIPT,
    LogFramework.BUNYAN: Language.TYPESCRIPT,
    LogFramework.ZAP: Language.GO,
    LogFramework.LOGRUS: Language.GO,
    LogFramework.ZEROLOG: Language.GO,
    LogFramework.UNKNOWN: Language.UNKNOWN,
}

# ---------------------------------------------------------------------------
# Per-framework rule builders
# ---------------------------------------------------------------------------


def _python_logging_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    kwargs_example = ", ".join(f'"{f}": ...' for f in fields)
    kwargs_good = ", ".join(f'"{f}": ctx.{f}' for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "python_logging",
        "description": (
            f"Every logging call must supply {fields!r} as keys inside the "
            "`extra={}` keyword argument."
        ),
        "check_strategy": "regex+extra-dict",
        "patterns": {
            "log_call": r"\b(?:logger|logging|log)\.(debug|info|warning|warn|error|critical|exception)\s*\(",
            "extra_kwarg": r"\bextra\s*=\s*\{",
            "required_keys": fields,
        },
        "message_template": (
            "Log call is missing required structured fields: {missing}. "
            f"Add them via `extra={{{kwargs_example}}}`."
        ),
        "severity": config.severity.value,
        "references": [
            "https://docs.python.org/3/library/logging.html#logging.Logger.debug"
        ],
        "examples": {
            "good": [
                f"logger.info('user signed in', extra={{{kwargs_good}}})",
            ],
            "bad": [
                "logger.info('user signed in')",
                f"logger.info('user signed in', extra={{'{fields[0]}': ...}})"
                if len(fields) > 1
                else "logger.info('user signed in')",
            ],
        },
    }


def _structlog_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    kwargs_sig = ", ".join(f"{f}=..." for f in fields)
    kwargs_good = ", ".join(f"{f}=ctx.{f}" for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "structlog",
        "description": (
            f"Every structlog call must include {fields!r} as keyword arguments."
        ),
        "check_strategy": "regex+kwargs",
        "patterns": {
            "log_call": r"\b(?:log|logger)\.(debug|info|warning|warn|error|critical)\s*\(",
            "required_kwargs": fields,
        },
        "message_template": (
            "structlog call is missing required fields: {missing}. "
            f"Pass them as keyword arguments: `log.info('msg', {kwargs_sig})`."
        ),
        "severity": config.severity.value,
        "references": ["https://www.structlog.org/en/stable/"],
        "examples": {
            "good": [
                f"log.info('request received', {kwargs_good})",
                f"logger.bind({kwargs_good}).info('request received')",
            ],
            "bad": [
                "log.info('request received')",
                f"log.info('request received', {fields[0]}=...)" if len(fields) > 1 else "log.info('request received')",
            ],
        },
    }


def _loguru_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    kwargs_bind = ", ".join(f"{f}=ctx.{f}" for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "loguru",
        "description": (
            f"Every loguru call must include {fields!r} via `.bind()` or as keyword args."
        ),
        "check_strategy": "regex+bind-or-kwargs",
        "patterns": {
            "log_call": r"\b(?:logger|log)\.(debug|info|warning|warn|error|critical|exception)\s*\(",
            "bind_call": r"\.bind\s*\(",
            "required_kwargs": fields,
        },
        "message_template": (
            "loguru call is missing required fields: {missing}. "
            f"Use `logger.bind({kwargs_bind}).info('msg')` or pass fields as keyword args."
        ),
        "severity": config.severity.value,
        "references": ["https://loguru.readthedocs.io/en/stable/"],
        "examples": {
            "good": [
                f"logger.bind({kwargs_bind}).info('charge processed')",
                f"logger.info('charge processed', {kwargs_bind})",
            ],
            "bad": [
                "logger.info('charge processed')",
                f"logger.bind({fields[0]}=...).info('charge processed')" if len(fields) > 1 else "logger.info('charge processed')",
            ],
        },
    }


def _winston_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    meta_good = ", ".join(f"{f}: ctx.{f}" for f in fields)
    selector = "CallExpression[callee.property.name=/^(debug|info|warn|error)$/]"
    return {
        "rule_id": "structured-log-fields",
        "framework": "winston",
        "description": (
            f"Every winston log call must include {fields!r} in the metadata object."
        ),
        "check_strategy": "regex+object-keys",
        "patterns": {
            "log_call": r"\b(?:logger|log)\.(debug|info|warn|error)\s*\(",
            "required_keys": fields,
        },
        "message_template": (
            "Winston log call is missing required metadata fields: {missing}. "
            f"Add them to the metadata object: `logger.info('msg', {{ {meta_good} }})`."
        ),
        "severity": config.severity.value,
        "eslint_config_snippet": {
            "rules": {
                "no-restricted-syntax": [
                    "error",
                    {
                        "selector": selector,
                        "message": f"Log calls must include structured fields: {fields}",
                    },
                ]
            }
        },
        "references": ["https://github.com/winstonjs/winston"],
        "examples": {
            "good": [
                f"logger.info('user login', {{ {meta_good} }})",
            ],
            "bad": [
                "logger.info('user login')",
                f"logger.info('user login', {{ {fields[0]}: ... }})" if len(fields) > 1 else "logger.info('user login')",
            ],
        },
    }


def _pino_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    meta_good = ", ".join(f"{f}: ctx.{f}" for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "pino",
        "description": (
            f"Every pino log call must include {fields!r} as top-level keys in the first object arg."
        ),
        "check_strategy": "regex+object-keys",
        "patterns": {
            "log_call": r"\b(?:logger|log)\.(debug|info|warn|error|fatal|trace)\s*\(",
            "required_keys": fields,
        },
        "message_template": (
            "Pino log call is missing required fields: {missing}. "
            f"Pass them as the first object argument: `log.info({{ {meta_good} }}, 'msg')`."
        ),
        "severity": config.severity.value,
        "references": ["https://getpino.io/"],
        "examples": {
            "good": [
                f"log.info({{ {meta_good} }}, 'order created')",
            ],
            "bad": [
                "log.info('order created')",
                f"log.info({{ {fields[0]}: ... }}, 'order created')" if len(fields) > 1 else "log.info('order created')",
            ],
        },
    }


def _bunyan_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    meta_good = ", ".join(f"{f}: ctx.{f}" for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "bunyan",
        "description": (
            f"Every bunyan log call must include {fields!r} in the fields object."
        ),
        "check_strategy": "regex+object-keys",
        "patterns": {
            "log_call": r"\b(?:logger|log)\.(debug|info|warn|error|fatal|trace)\s*\(",
            "required_keys": fields,
        },
        "message_template": (
            "Bunyan log call is missing required fields: {missing}. "
            f"Pass them as the first object: `log.info({{ {meta_good} }}, 'msg')`."
        ),
        "severity": config.severity.value,
        "references": ["https://github.com/trentm/node-bunyan"],
        "examples": {
            "good": [
                f"log.info({{ {meta_good} }}, 'request handled')",
            ],
            "bad": [
                "log.info('request handled')",
            ],
        },
    }


def _zap_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    zap_fields = ", ".join(f'zap.String("{f}", ...)' for f in fields)
    zap_good = ", ".join(f'zap.String("{f}", ctx.{f})' for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "zap",
        "description": (
            f"Every zap log call must include {fields!r} as zap.Field arguments."
        ),
        "check_strategy": "regex+zap-fields",
        "patterns": {
            "log_call": r'\blogger\.(Debug|Info|Warn|Error|Fatal|Panic|DPanic)\s*\(',
            "required_string_fields": fields,
            "field_pattern": r'zap\.(?:String|Field)\s*\(\s*"({field})"',
        },
        "message_template": (
            "Zap log call is missing required fields: {missing}. "
            f'Add `{zap_fields}` as positional arguments.'
        ),
        "severity": config.severity.value,
        "references": ["https://pkg.go.dev/go.uber.org/zap"],
        "examples": {
            "good": [
                f'logger.Info("request handled", {zap_good})',
            ],
            "bad": [
                'logger.Info("request handled")',
                f'logger.Info("request handled", zap.String("{fields[0]}", ...))' if len(fields) > 1 else 'logger.Info("request handled")',
            ],
        },
    }


def _logrus_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    fields_map = ", ".join(f'"{f}": ctx.{f}' for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "logrus",
        "description": (
            f"Every logrus call must include {fields!r} via WithFields or WithField."
        ),
        "check_strategy": "regex+with-fields",
        "patterns": {
            "log_call": r'\b(?:logrus|log|logger)\.(Debug|Info|Warn|Warning|Error|Fatal|Panic|Print)\s*\(',
            "with_fields": r'\.WithFields\s*\(\s*logrus\.Fields\s*\{',
            "required_keys": fields,
        },
        "message_template": (
            "Logrus call is missing required fields: {missing}. "
            f'Use `logrus.WithFields(logrus.Fields{{{fields_map}}}).Info("msg")`.'
        ),
        "severity": config.severity.value,
        "references": ["https://github.com/sirupsen/logrus"],
        "examples": {
            "good": [
                f'logrus.WithFields(logrus.Fields{{{fields_map}}}).Info("user login")',
            ],
            "bad": [
                'logrus.Info("user login")',
                f'logrus.WithFields(logrus.Fields{{"{fields[0]}": ...}}).Info("user login")' if len(fields) > 1 else 'logrus.Info("user login")',
            ],
        },
    }


def _zerolog_rules(config: LogLinterConfig) -> dict:
    fields = config.required_fields
    chain = "".join(f'.Str("{f}", ctx.{f})' for f in fields)
    return {
        "rule_id": "structured-log-fields",
        "framework": "zerolog",
        "description": (
            f"Every zerolog log call must chain {fields!r} using .Str() / .Interface()."
        ),
        "check_strategy": "regex+zerolog-chain",
        "patterns": {
            "log_call": r'\b(?:log|logger)\.(Debug|Info|Warn|Error|Fatal|Panic)\s*\(\)',
            "required_chain_fields": fields,
            "field_pattern": r'\.(?:Str|Interface)\s*\(\s*"({field})"',
        },
        "message_template": (
            "zerolog event is missing required fields: {missing}. "
            f"Chain{chain}.Msg('...')` before the final .Msg() call."
        ),
        "severity": config.severity.value,
        "references": ["https://github.com/rs/zerolog"],
        "examples": {
            "good": [
                f'log.Info(){chain}.Msg("request handled")',
            ],
            "bad": [
                'log.Info().Msg("request handled")',
            ],
        },
    }


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_RULE_BUILDERS = {
    LogFramework.PYTHON_LOGGING: _python_logging_rules,
    LogFramework.STRUCTLOG: _structlog_rules,
    LogFramework.LOGURU: _loguru_rules,
    LogFramework.WINSTON: _winston_rules,
    LogFramework.PINO: _pino_rules,
    LogFramework.BUNYAN: _bunyan_rules,
    LogFramework.ZAP: _zap_rules,
    LogFramework.LOGRUS: _logrus_rules,
    LogFramework.ZEROLOG: _zerolog_rules,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_rules(
    framework: LogFramework,
    config: LogLinterConfig | None = None,
) -> GeneratorResult:
    """Generate structured-log linter rules for *framework*.

    Parameters
    ----------
    framework:
        The logging framework to generate rules for.  Use
        :func:`~log_format_linter.detect_framework` to auto-detect this.
    config:
        Linter configuration.  Defaults to :class:`LogLinterConfig` (requires
        ``domain`` and ``trace_id`` on every log call).

    Returns
    -------
    GeneratorResult
        Contains the generated rules dict, human-readable description, and
        good/bad code examples.
    """
    if config is None:
        config = LogLinterConfig()

    lang = _LANGUAGE_MAP.get(framework, Language.UNKNOWN)
    builder = _RULE_BUILDERS.get(framework)

    if builder is None:
        rules: dict = {}
        description = (
            f"No built-in rules for framework '{framework.value}'. "
            "Use the default LogLinterConfig as a starting point and implement "
            "custom check_strategy logic in checker.py."
        )
        examples: list[dict[str, str]] = []
    else:
        rules = builder(config)
        description = rules.get("description", "")
        raw_examples = rules.get("examples", {})
        examples = []
        for code in raw_examples.get("good", []):
            examples.append({"type": "good", "code": code})
        for code in raw_examples.get("bad", []):
            examples.append({"type": "bad", "code": code})

    return GeneratorResult(
        framework=framework,
        language=lang,
        config=config,
        rules=rules,
        description=description,
        examples=examples,
    )
