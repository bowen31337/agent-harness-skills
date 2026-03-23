# Evaluation Gates — agent-harness-skills

← [AGENTS.md](../../AGENTS.md)

Gates are pass/fail checks that run during `harness evaluate`.  Each gate emits a
`GateResult` (with `rule_id`, `severity`, zero or more `Violation` objects, and a boolean
`passed` flag).  All gate logic lives in `harness_skills/gates/` and is driven by
`harness.config.yaml`.

---

## Gate Inventory

| Gate | Class | Config key | Skill doc |
|------|-------|-----------|-----------|
| Line coverage | `CoverageGate` | `coverage` | `.claude/commands/harness/coverage-gate.md` |
| Docs freshness | `DocsFreshnessGate` | `docs_freshness` | `.claude/commands/harness/docs-freshness.md` |
| Security / CVE | `SecurityGate` | `security` | `.claude/commands/harness/security-check-gate.md` |
| Performance regression | `PerformanceGate` | `performance` | `.claude/commands/harness/performance.md` |
| Custom principles | `PrinciplesGate` | `principles` | `.claude/commands/harness/principles-gate.md` |
| Plugin gates (YAML-driven) | `PluginGateRunner` | `plugins[]` | `.claude/commands/harness/evaluate.md` |

---

## Running Gates

```bash
# All gates, JSON output
harness evaluate --config harness.config.yaml --format json

# Programmatic
from harness_skills.gates import GateEvaluator, run_gates
from harness_skills.models import EvaluateResponse

result: EvaluateResponse = run_gates("harness.config.yaml")
for gate in result.gates:
    if not gate.passed:
        for v in gate.violations:
            print(v.rule_id, v.message)
```

Exit code `0` = all gates passed.  Non-zero = at least one gate failed.

---

## Violation Shape

```python
from harness_skills.models import GateResult, Violation, Severity

# rule_id format:  namespace/kebab-slug
# e.g.  "coverage/line-rate", "security/known-cve", "docs/stale-file"
v = Violation(
    rule_id="coverage/line-rate",
    severity=Severity.ERROR,
    message="Line coverage 71 % is below threshold 80 %",
    file="harness_skills/gates/coverage.py",
    line=42,
)
```

`Severity` values (ascending): `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`.

---

## Configuring Gates (`harness.config.yaml`)

```yaml
coverage:
  enabled: true
  threshold: 80          # minimum line-coverage percentage

docs_freshness:
  enabled: true
  max_age_days: 30       # flag docs not touched in N days

security:
  enabled: true
  fail_on_severity: high # block on high/critical CVEs

performance:
  enabled: true
  regression_threshold_pct: 10   # fail if p95 regresses > 10 %

principles:
  enabled: true
  rules_file: .claude/principles.yaml

plugins:                 # zero or more YAML-driven custom gates
  - name: my-custom-gate
    script: scripts/check_something.py
    fail_on: error
```

Full annotated reference: `harness.config.yaml` (16 KB) at repo root.

---

## Adding a Plugin Gate (No Python Required)

```yaml
# harness.config.yaml
plugins:
  - name: no-hardcoded-secrets
    script: scripts/scan_secrets.sh
    fail_on: warning
    timeout_seconds: 30
```

The script must exit `0` (pass) or non-zero (fail) and may write JSON violations to
stdout (`[{"rule_id": "…", "severity": "error", "message": "…"}]`).

See `harness_skills/plugins/` for the full plugin model.

---

## Module Boundary Rules for Gates

Always import from the package root:

```python
# ✅ correct
from harness_skills.gates import CoverageGate, GateEvaluator, run_gates
from harness_skills.models import GateResult, Violation, Severity

# ❌ forbidden — violates MB001
from harness_skills.gates.coverage import CoverageGate
```

---

## Deeper References

- **Gate config schema** → `harness.config.yaml` (annotated, repo root)
- **Principles rules** → `PRINCIPLES.md` (30 KB, full rule catalogue)
- **Error handling model** → `ERROR_HANDLING_RULES.md` (12 KB)
- **Coverage gate skill** → `.claude/commands/harness/coverage-gate.md`
- **Security gate skill** → `.claude/commands/harness/security-check-gate.md`
- **Performance gate skill** → `.claude/commands/harness/performance.md`
- **Full evaluate skill** → `.claude/commands/harness/evaluate.md`
- **Architecture / boundary graph** → [ARCHITECTURE.md](../../ARCHITECTURE.md)
