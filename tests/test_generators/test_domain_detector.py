"""Tests for domain boundary detection."""

from __future__ import annotations

from pathlib import Path

from harness_skills.generators.domain_detector import DetectedDomain, detect_domains
from harness_skills.utils.import_graph import ImportEdge, ImportGraph


class TestDetectDomains:

    def test_empty_dir(self, tmp_path: Path) -> None:
        domains = detect_domains(tmp_path)
        assert domains == []

    def test_detect_python_packages(self, tmp_path: Path) -> None:
        auth = tmp_path / "auth"
        auth.mkdir()
        (auth / "__init__.py").write_text("")
        (auth / "login.py").write_text("pass")
        (auth / "session.py").write_text("pass")

        billing = tmp_path / "billing"
        billing.mkdir()
        (billing / "__init__.py").write_text("")
        (billing / "invoice.py").write_text("pass")
        (billing / "payment.py").write_text("pass")

        domains = detect_domains(tmp_path)
        names = {d.name for d in domains}
        assert "auth" in names
        assert "billing" in names

    def test_src_subdirectories(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        for name in ("components", "utils"):
            d = src / name
            d.mkdir()
            (d / "index.ts").write_text("export {}")
            (d / "helper.ts").write_text("export {}")

        domains = detect_domains(tmp_path)
        names = {d.name for d in domains}
        assert "components" in names
        assert "utils" in names

    def test_min_files_filter(self, tmp_path: Path) -> None:
        small = tmp_path / "tiny"
        small.mkdir()
        (small / "one.py").write_text("pass")  # Only 1 file

        domains = detect_domains(tmp_path, min_files=2)
        assert not any(d.name == "tiny" for d in domains)

    def test_excludes_test_dirs(self, tmp_path: Path) -> None:
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text("pass")
        (tests / "test_bar.py").write_text("pass")

        domains = detect_domains(tmp_path)
        assert not any(d.name == "tests" for d in domains)

    def test_import_graph_enrichment(self, tmp_path: Path) -> None:
        auth = tmp_path / "auth"
        auth.mkdir()
        (auth / "a.py").write_text("")
        (auth / "b.py").write_text("")

        graph = ImportGraph(edges=[
            ImportEdge("auth.a", "auth.b"),
            ImportEdge("auth.a", "external.lib"),
        ])

        domains = detect_domains(tmp_path, import_graph=graph)
        auth_domain = next((d for d in domains if d.name == "auth"), None)
        assert auth_domain is not None
        assert auth_domain.confidence > 0.3
