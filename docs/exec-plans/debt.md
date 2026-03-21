# Technical Debt Tracker

> Agents append entries below using `skills/debt_tracker.py`.
> Each entry records a known shortcut, compromise, or TODO with severity and a clear path to remediation.

---

## Severity Key

| Severity | Meaning |
|----------|---------|
| 🔴 **critical** | Blocks correctness, security, or production safety. Remediate before next release. |
| 🟠 **high**     | Degrades reliability or maintainability significantly. Remediate within 1–2 sprints. |
| 🟡 **medium**   | Noticeable friction or tech-debt accumulation. Remediate within the quarter. |
| 🟢 **low**      | Minor polish or nice-to-have. Track and batch into a cleanup sprint. |

---

## Open Debt

<!-- agents append new entries here — do not remove this comment -->

| ID | Severity | Area / File | Description | Remediation Notes | Logged By | Logged At | Status |
|----|----------|-------------|-------------|-------------------|-----------|-----------|--------|
| DEBT-002 | 🟡 **medium** | src/api/rate_limit.py | TODO: rate-limiting is a hard-coded 100 req/min constant — not configurable per tenant | Load limit from tenant config / env var; add integration test for custom limits | agent/coder-v1 | 2026-03-13 01:34 UTC | open |
| DEBT-001 | 🟠 **high** | src/auth/middleware.py | Auth token validated only in middleware, not in the service layer — callers that bypass HTTP middleware skip validation entirely | Move token validation into AuthService.verify(); make middleware delegate to it so any caller path is covered | agent/planner-v1 | 2026-03-13 01:34 UTC | open |

---

## Resolved Debt

<!-- move entries here when remediation is complete -->

| ID | Severity | Area / File | Description | Resolution | Resolved By | Resolved At |
|----|----------|-------------|-------------|------------|-------------|-------------|

| DEBT-003 | 🟢 **low** | skills/debt_tracker.py | No async support; all file I/O is blocking | Removed smoke-test entry — no real async requirement at this time | agent/smoke-test | 2026-03-14 08:17 UTC |
---

## Debt Summary

_Updated automatically by `skills/debt_tracker.py` on each run._

| Metric | Count |
|--------|-------|
| Total open | 2 |
| Critical | 0 |
| High | 1 |
| Medium | 1 |
| Low | 0 |
| Resolved (all time) | 1 |
