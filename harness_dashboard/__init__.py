"""
harness_dashboard — Harness Effectiveness Scoring & Dashboard

Correlates harness artifact usage with PR quality metrics (gate pass rate,
review cycles, time to merge) and renders a Rich terminal dashboard.

Public API
----------
    compute_scores    — score a list of HarnessRecord objects
    render_dashboard  — render the Rich terminal dashboard
    generate_dataset  — generate a synthetic dataset for testing / demos
    ArtifactType      — enum of harness artifact types
    HarnessRecord     — per-PR harness-usage record (Pydantic model)
    PRRecord          — per-PR quality metrics record (Pydantic model)
"""

__version__ = "0.1.0"

from harness_dashboard.data_generator import generate_dataset
from harness_dashboard.dashboard import render_dashboard
from harness_dashboard.models import ArtifactType, HarnessRecord, PRRecord
from harness_dashboard.scorer import compute_scores

__all__ = [
    "compute_scores",
    "render_dashboard",
    "generate_dataset",
    "ArtifactType",
    "HarnessRecord",
    "PRRecord",
]
