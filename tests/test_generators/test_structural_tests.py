"""Tests for structural test generation."""

from __future__ import annotations

from pathlib import Path

from harness_skills.generators.domain_detector import DetectedDomain
from harness_skills.generators.structural_tests import generate_structural_tests


class TestGenerateStructuralTests:

    def test_generates_valid_python(self, tmp_path: Path) -> None:
        domains = [
            DetectedDomain(name="auth", root_path="auth", file_count=5),
            DetectedDomain(name="billing", root_path="billing", file_count=3),
        ]
        code = generate_structural_tests(tmp_path, domains)
        assert "class TestDomain_auth:" in code
        assert "class TestDomain_billing:" in code
        # Verify it's valid Python
        compile(code, "<test>", "exec")

    def test_with_layer_order(self, tmp_path: Path) -> None:
        domains = [DetectedDomain(name="core", root_path="core")]
        code = generate_structural_tests(
            tmp_path, domains, layer_order=["types", "service", "api"]
        )
        assert "TestLayerOrder" in code
        assert "LAYER_ORDER" in code

    def test_writes_to_output_dir(self, tmp_path: Path) -> None:
        domains = [DetectedDomain(name="app", root_path="app")]
        out = tmp_path / "generated_tests"
        generate_structural_tests(tmp_path, domains, output_dir=out)
        assert (out / "test_structural.py").exists()

    def test_empty_domains(self, tmp_path: Path) -> None:
        code = generate_structural_tests(tmp_path, [])
        assert "TestCodebaseIntegrity" in code
        compile(code, "<test>", "exec")
