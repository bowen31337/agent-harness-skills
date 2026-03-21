from __future__ import annotations
import textwrap
from datetime import date, timedelta
from pathlib import Path
import pytest
from harness_skills.gates.docs_freshness import (
    DocsFreshnessGate, GateConfig,
    _extract_file_refs, _looks_like_file_path, _parse_generated_at,
)

TODAY = date(2025, 6, 15)
TS    = "<!-- generated_at: 2025-06-14 -->"   # fresh timestamp fixture


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    monkeypatch.setattr("harness_skills.gates.docs_freshness._today", lambda: TODAY)


def agents(tmp_path, content, sub=""):
    d = tmp_path / sub if sub else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / "AGENTS.md"
    f.write_text(textwrap.dedent(content))
    return f


def touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


# ---------------------------------------------------------------------------
# _looks_like_file_path
# ---------------------------------------------------------------------------
def test_py_file():          assert _looks_like_file_path("src/foo.py")
def test_dot_slash():        assert _looks_like_file_path("./hs/gate.py")
def test_yaml_file():        assert _looks_like_file_path("config/s.yaml")
def test_url_rejected():     assert not _looks_like_file_path("https://x.com/f.py")
def test_anchor_rejected():  assert not _looks_like_file_path("#sec")
def test_empty_rejected():   assert not _looks_like_file_path("")
def test_bare_word():        assert not _looks_like_file_path("readme")
def test_slash_no_ext():     assert _looks_like_file_path("scripts/deploy")


# ---------------------------------------------------------------------------
# _parse_generated_at
# ---------------------------------------------------------------------------
def test_html_comment():
    assert _parse_generated_at(f"<!-- generated_at: 2024-03-01 -->") == date(2024, 3, 1)

def test_bare_kv():
    assert _parse_generated_at("generated_at: 2023-12-31") == date(2023, 12, 31)

def test_blockquote():
    assert _parse_generated_at("> generated_at: 2025-01-10") == date(2025, 1, 10)

def test_absent():
    assert _parse_generated_at("# nothing") is None

def test_first_wins():
    c = "generated_at: 2024-01-01\ngenerated_at: 2024-06-01"
    assert _parse_generated_at(c) == date(2024, 1, 1)


# ---------------------------------------------------------------------------
# _extract_file_refs
# ---------------------------------------------------------------------------
def test_md_link():
    assert "src/models/foo.py" in dict(_extract_file_refs("See [m](src/models/foo.py)."))

def test_anchor_excluded():
    assert _extract_file_refs("See [h](#sec).") == []

def test_backtick_path():
    assert "hs/telemetry.py" in dict(_extract_file_refs("Edit `hs/telemetry.py`."))

def test_bare_word_excl():
    assert _extract_file_refs("Run `pytest`.") == []

def test_url_excl():
    assert _extract_file_refs("See https://x.com/f.py.") == []

def test_line_number():
    refs = _extract_file_refs("line\n[ref](src/foo.py)\nline3")
    m = [(p, ln) for p, ln in refs if p == "src/foo.py"]
    assert m and m[0][1] == 2

def test_same_line_dedup():
    assert [p for p, _ in _extract_file_refs("[A](src/f.py) [B](src/f.py)")].count("src/f.py") == 1


# ---------------------------------------------------------------------------
# Dead-reference checks
# ---------------------------------------------------------------------------
def test_existing_ref_ok(tmp_path):
    touch(tmp_path / "src" / "models" / "foo.py")
    agents(tmp_path, TS + "\n[foo](src/models/foo.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    assert not [v for v in r.violations if v.kind == "dead_ref"]

def test_missing_ref_violation(tmp_path):
    agents(tmp_path, TS + "\n[ghost](src/ghost.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    dead = [v for v in r.violations if v.kind == "dead_ref"]
    assert len(dead) == 1 and "src/ghost.py" in dead[0].message

def test_line_number_recorded(tmp_path):
    agents(tmp_path, TS + "\n## h\n\n[ghost](src/ghost.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    dead = [v for v in r.violations if v.kind == "dead_ref"]
    assert dead[0].line_number == 4

def test_relative_to_agents_dir(tmp_path):
    sub = tmp_path / "svc" / "auth"
    touch(sub / "utils" / "helpers.py")
    agents(tmp_path, TS + "\n[h](utils/helpers.py)\n", "svc/auth")
    r = DocsFreshnessGate().run(tmp_path)
    assert not [v for v in r.violations if v.kind == "dead_ref"]

def test_fail_on_error_false_warns(tmp_path):
    agents(tmp_path, TS + "\n[d](no_file.py)\n")
    r = DocsFreshnessGate(GateConfig(fail_on_error=False)).run(tmp_path)
    dead = [v for v in r.violations if v.kind == "dead_ref"]
    assert dead[0].severity == "warning" and r.passed

def test_fail_on_error_true_fails(tmp_path):
    agents(tmp_path, TS + "\n[d](missing.py)\n")
    assert not DocsFreshnessGate(GateConfig(fail_on_error=True)).run(tmp_path).passed


# ---------------------------------------------------------------------------
# Freshness / timestamp checks
# ---------------------------------------------------------------------------
def test_fresh_ok(tmp_path):
    agents(tmp_path, TS + "\n# AGENTS\n")
    r = DocsFreshnessGate().run(tmp_path)
    assert not [v for v in r.violations if v.kind in ("stale_content", "missing_timestamp")]

def test_stale_violation(tmp_path):
    agents(tmp_path, f"<!-- generated_at: 2025-04-16 -->\n# AGENTS\n")
    r = DocsFreshnessGate().run(tmp_path)
    stale = [v for v in r.violations if v.kind == "stale_content"]
    assert len(stale) == 1 and "60 day" in stale[0].message

def test_exactly_at_threshold_ok(tmp_path):
    from datetime import timedelta
    gen = TODAY - timedelta(days=30)
    agents(tmp_path, f"<!-- generated_at: {gen} -->\n# AGENTS\n")
    r = DocsFreshnessGate(GateConfig(max_staleness_days=30)).run(tmp_path)
    assert not [v for v in r.violations if v.kind == "stale_content"]

def test_one_over_threshold(tmp_path):
    from datetime import timedelta
    gen = TODAY - timedelta(days=31)
    agents(tmp_path, f"<!-- generated_at: {gen} -->\n# AGENTS\n")
    r = DocsFreshnessGate(GateConfig(max_staleness_days=30)).run(tmp_path)
    assert len([v for v in r.violations if v.kind == "stale_content"]) == 1

def test_missing_timestamp(tmp_path):
    agents(tmp_path, "# AGENTS\nNo date.\n")
    r = DocsFreshnessGate().run(tmp_path)
    assert len([v for v in r.violations if v.kind == "missing_timestamp"]) == 1

def test_missing_ts_warning_no_fail(tmp_path):
    agents(tmp_path, "# AGENTS\n")
    r = DocsFreshnessGate(GateConfig(fail_on_error=False)).run(tmp_path)
    miss = [v for v in r.violations if v.kind == "missing_timestamp"]
    assert miss[0].severity == "warning" and r.passed


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def test_finds_root(tmp_path):
    agents(tmp_path, TS + "\n")
    assert len(DocsFreshnessGate().run(tmp_path).checked_files) == 1

def test_finds_nested(tmp_path):
    agents(tmp_path, TS + "\n")
    agents(tmp_path, TS + "\n", "svc/auth")
    assert len(DocsFreshnessGate().run(tmp_path).checked_files) == 2

def test_skips_venv(tmp_path):
    agents(tmp_path, TS + "\n")
    agents(tmp_path, "# shadow\n", ".venv/lib")
    assert len(DocsFreshnessGate().run(tmp_path).checked_files) == 1

def test_empty_repo_passes(tmp_path):
    r = DocsFreshnessGate().run(tmp_path)
    assert r.passed and r.checked_files == []


# ---------------------------------------------------------------------------
# Stats and helpers
# ---------------------------------------------------------------------------
def test_stats_populated(tmp_path):
    touch(tmp_path / "src" / "real.py")
    agents(tmp_path, "# no ts\n[real](src/real.py)\n[dead](src/ghost.py)\n")
    s = DocsFreshnessGate().run(tmp_path).stats
    assert s["agents_files"] == 1 and s["dead_refs"] >= 1
    assert s["missing_timestamps"] == 1 and s["total_refs_checked"] >= 2

def test_errors_helper(tmp_path):
    agents(tmp_path, "# no ts\n[dead](missing.py)\n")
    r = DocsFreshnessGate(GateConfig(fail_on_error=True)).run(tmp_path)
    assert r.errors() and all(v.severity == "error" for v in r.errors())

def test_summary_format(tmp_path):
    agents(tmp_path, "# no ts\n")
    for v in DocsFreshnessGate().run(tmp_path).violations:
        assert v.kind in v.summary() and str(v.agents_file) in v.summary()


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------
def test_fully_valid_passes(tmp_path):
    touch(tmp_path / "harness_skills" / "telemetry.py")
    touch(tmp_path / "harness_skills" / "models" / "gate_configs.py")
    content = (
        f"<!-- generated_at: {TODAY} -->\n# AGENTS\n\n"
        "- [Telemetry](harness_skills/telemetry.py)\n"
        "- [Gate configs](harness_skills/models/gate_configs.py)\n"
    )
    agents(tmp_path, content)
    r = DocsFreshnessGate(GateConfig(max_staleness_days=30, fail_on_error=True)).run(tmp_path)
    assert r.passed and not r.violations

def test_stale_plus_dead_reported(tmp_path):
    agents(tmp_path, f"<!-- generated_at: 2020-01-01 -->\n[dead](src/gone.py)\n")
    r = DocsFreshnessGate(GateConfig(fail_on_error=False)).run(tmp_path)
    kinds = {v.kind for v in r.violations}
    assert "dead_ref" in kinds and "stale_content" in kinds
