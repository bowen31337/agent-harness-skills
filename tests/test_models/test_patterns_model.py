"""Tests for harness_skills.models.patterns — 100% coverage target."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness_skills.models.patterns import PatternFrequencyModel


class TestPatternFrequencyModel:
    def test_minimal(self):
        p = PatternFrequencyModel(pattern_name="singleton", category="creational")
        assert p.occurrences == 0
        assert p.example_files == []
        assert p.suggested_principle == ""

    def test_full(self):
        p = PatternFrequencyModel(
            pattern_name="factory",
            category="creational",
            occurrences=5,
            example_files=["a.py", "b.py"],
            suggested_principle="Use factory pattern for object creation",
        )
        assert p.occurrences == 5
        assert len(p.example_files) == 2
        assert p.suggested_principle.startswith("Use")

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            PatternFrequencyModel(pattern_name="x")  # missing category
        with pytest.raises(ValidationError):
            PatternFrequencyModel(category="y")  # missing pattern_name

    def test_roundtrip(self):
        p = PatternFrequencyModel(
            pattern_name="observer",
            category="behavioral",
            occurrences=3,
            example_files=["c.py"],
            suggested_principle="Use observer for events",
        )
        assert PatternFrequencyModel.model_validate(p.model_dump()) == p

    def test_roundtrip_json(self):
        p = PatternFrequencyModel(pattern_name="p", category="c")
        restored = PatternFrequencyModel.model_validate_json(p.model_dump_json())
        assert restored == p
