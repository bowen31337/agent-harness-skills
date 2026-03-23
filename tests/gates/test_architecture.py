"""
tests/gates/test_architecture.py
==================================
Unit tests for the architecture (import-layer) gate and custom layer
definitions feature.

Test strategy
-------------
**Default layer_order (backward compat)**
* Clean project with no violations passes.
* Inner layer importing from outer layer produces an error.
* ``report_only=True`` downgrades errors to warnings.
* Files outside any layer are skipped entirely.
* Syntax-error Python files are skipped (no crash).
* Files inside ``.venv`` / ``__pycache__`` are excluded.

**arch_style presets**
* Each built-in preset (layered, clean, hexagonal, mvc, ddd) resolves the
  correct layer order and aliases.
* An unknown ``arch_style`` falls back to ``layer_order``.
* Violation detected when inner-layer file imports outer-layer module via an
  alias name (validates alias resolution works end-to-end).

**layer_definitions (custom)**
* Custom layer_definitions override both arch_style and layer_order.
* Aliases in layer_definitions are used for detection.
* layer_definitions priority over arch_style when both set.
* Empty layer_definitions list falls back to layer_order.
* layer_definitions with explicit ranks are sorted correctly.
* Violation detected correctly using custom definitions.
* No violation when imports flow in the allowed direction.

**ArchitectureGateConfig model**
* New fields have correct defaults.
* model_dump() includes the new fields.
* model_validate() parses arch_style and layer_definitions from a dict.
* Backward compat: config without new fields still works.

**ARCHITECTURE_STYLE_PRESETS**
* All expected style keys are present.
* Each preset has layers sorted by ascending rank.
* Hexagonal, clean, mvc, ddd, and layered presets have the expected inner
  (rank-0) layer name.

**_resolve_layer_definitions**
* Returns plain layer_order when no arch_style or layer_definitions set.
* Returns preset layers when arch_style matches a known preset.
* Returns normalised custom dicts when layer_definitions is set.
* Prioritises layer_definitions over arch_style.
* Unknown arch_style falls back to layer_order.

**_render_architecture (config generator)**
* Emits arch_style field when set.
* Emits layer_definitions block when set.
* Emits layer_order when neither arch_style nor layer_definitions set.
* All existing renderer assertions still pass.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from harness_skills.gates.runner import (
    check_architecture,
    _resolve_layer_definitions,
)
from harness_skills.generators.config_generator import _render_architecture
from harness_skills.models.gate_configs import (
    ARCHITECTURE_STYLE_PRESETS,
    ArchitectureGateConfig,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    """Write *content* to *tmp_path / rel* (creates parent dirs)."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _cfg(**kwargs) -> ArchitectureGateConfig:
    """Return an :class:`ArchitectureGateConfig` with test-friendly defaults."""
    defaults: dict = {
        "enabled": True,
        "fail_on_error": True,
        "report_only": False,
    }
    defaults.update(kwargs)
    return ArchitectureGateConfig(**defaults)


# ===========================================================================
# Default layer_order — backward compatibility
# ===========================================================================


class TestDefaultLayerOrder:
    def test_clean_project_no_violations(self, tmp_path: Path) -> None:
        """services/ importing from models/ is legal — no violation."""
        _write(tmp_path, "models/user.py", "class User: pass\n")
        _write(
            tmp_path,
            "services/user_service.py",
            "from models import User\n\nclass UserService: pass\n",
        )
        cfg = _cfg(layer_order=["models", "services"])
        assert check_architecture(tmp_path, cfg) == []

    def test_inner_layer_importing_outer_raises_error(self, tmp_path: Path) -> None:
        """models/ importing from services/ is an upward violation."""
        _write(tmp_path, "services/user_service.py", "class UserService: pass\n")
        _write(
            tmp_path,
            "models/user.py",
            "from services import UserService\n\nclass User: pass\n",
        )
        cfg = _cfg(layer_order=["models", "services"])
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        f = failures[0]
        assert f.severity == "error"
        assert "models" in f.message
        assert "services" in f.message
        assert f.rule_id == "arch/layer-violation"

    def test_report_only_emits_warning_not_error(self, tmp_path: Path) -> None:
        """report_only=True turns errors into warnings."""
        _write(tmp_path, "services/svc.py", "class Svc: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "from services import Svc\n",
        )
        cfg = _cfg(layer_order=["models", "services"], report_only=True)
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        assert all(f.severity == "warning" for f in failures)

    def test_files_outside_any_layer_skipped(self, tmp_path: Path) -> None:
        """A file not belonging to any known layer produces no violation."""
        _write(tmp_path, "utils/helpers.py", "import os\n")
        cfg = _cfg(layer_order=["models", "services"])
        assert check_architecture(tmp_path, cfg) == []

    def test_syntax_error_file_skipped(self, tmp_path: Path) -> None:
        """Unparseable Python files don't crash the gate."""
        _write(tmp_path, "models/broken.py", "def oops(\n")
        cfg = _cfg(layer_order=["models", "services"])
        # Should not raise; result may be empty or have other failures
        result = check_architecture(tmp_path, cfg)
        assert isinstance(result, list)

    def test_venv_directory_excluded(self, tmp_path: Path) -> None:
        """Files inside .venv/ are never scanned."""
        _write(
            tmp_path,
            ".venv/lib/models/pkg.py",
            "from services import X\n",
        )
        cfg = _cfg(layer_order=["models", "services"])
        assert check_architecture(tmp_path, cfg) == []

    def test_pycache_excluded(self, tmp_path: Path) -> None:
        """Files inside __pycache__/ are never scanned."""
        _write(
            tmp_path,
            "models/__pycache__/user.cpython-312.pyc",
            "from services import X\n",
        )
        cfg = _cfg(layer_order=["models", "services"])
        assert check_architecture(tmp_path, cfg) == []

    def test_same_layer_import_allowed(self, tmp_path: Path) -> None:
        """Imports between files in the same layer are not violations."""
        _write(tmp_path, "services/a.py", "class A: pass\n")
        _write(tmp_path, "services/b.py", "from services.a import A\n")
        cfg = _cfg(layer_order=["models", "services"])
        assert check_architecture(tmp_path, cfg) == []

    def test_violation_includes_file_path_and_line_number(self, tmp_path: Path) -> None:
        """GateFailure.file_path and line_number are populated."""
        _write(tmp_path, "services/svc.py", "class Svc: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "\n\nfrom services import Svc\n",
        )
        cfg = _cfg(layer_order=["models", "services"])
        failures = check_architecture(tmp_path, cfg)
        assert failures
        assert failures[0].file_path is not None
        assert "models" in failures[0].file_path
        assert failures[0].line_number == 3

    def test_suggestion_names_allowed_layers(self, tmp_path: Path) -> None:
        """Suggestion lists the layers an inner layer may import from."""
        _write(tmp_path, "api/routes.py", "class Router: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "from api import Router\n",
        )
        cfg = _cfg(layer_order=["models", "repositories", "services", "api"])
        failures = check_architecture(tmp_path, cfg)
        assert failures
        # models has rank 0, so allowed list should be empty (innermost)
        assert "(none — this is the innermost layer)" in (failures[0].suggestion or "")

    def test_three_tier_violation_middle_to_outer(self, tmp_path: Path) -> None:
        """repositories/ importing from api/ is a violation."""
        _write(tmp_path, "api/routes.py", "class Router: pass\n")
        _write(
            tmp_path,
            "repositories/repo.py",
            "from api import Router\n",
        )
        cfg = _cfg(layer_order=["models", "repositories", "services", "api"])
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        assert any("repositories" in f.message for f in failures)


# ===========================================================================
# arch_style presets
# ===========================================================================


class TestArchStylePresets:
    def test_hexagonal_inner_layer_violation_detected(self, tmp_path: Path) -> None:
        """domain/ importing from infrastructure/ is an arch/layer violation."""
        _write(tmp_path, "infrastructure/db.py", "class DB: pass\n")
        _write(
            tmp_path,
            "domain/entity.py",
            "from infrastructure import DB\n",
        )
        cfg = _cfg(arch_style="hexagonal")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        assert any("domain" in f.message for f in failures)

    def test_hexagonal_outer_imports_inner_allowed(self, tmp_path: Path) -> None:
        """infrastructure/ importing from domain/ is allowed in hexagonal."""
        _write(tmp_path, "domain/entity.py", "class Entity: pass\n")
        _write(
            tmp_path,
            "infrastructure/repo.py",
            "from domain import Entity\n",
        )
        cfg = _cfg(arch_style="hexagonal")
        assert check_architecture(tmp_path, cfg) == []

    def test_hexagonal_alias_detection(self, tmp_path: Path) -> None:
        """'core' is an alias for 'domain' in hexagonal preset."""
        # 'adapters' has rank 2; 'core' is alias for 'domain' (rank 0)
        _write(tmp_path, "adapters/http.py", "class HttpAdapter: pass\n")
        _write(
            tmp_path,
            "core/entity.py",       # matches 'core' alias of 'domain'
            "from adapters import HttpAdapter\n",
        )
        cfg = _cfg(arch_style="hexagonal")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        # The canonical layer name 'domain' should appear in the message
        assert any("domain" in f.message for f in failures)

    def test_clean_style_entities_cannot_import_use_cases(self, tmp_path: Path) -> None:
        """entities/ (rank 0) importing use_cases/ (rank 1) is a violation."""
        _write(tmp_path, "use_cases/create_user.py", "class CreateUser: pass\n")
        _write(
            tmp_path,
            "entities/user.py",
            "from use_cases import CreateUser\n",
        )
        cfg = _cfg(arch_style="clean")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1

    def test_ddd_domain_cannot_import_presentation(self, tmp_path: Path) -> None:
        """domain/ (rank 0) importing from presentation/ (rank 3) is a violation."""
        _write(tmp_path, "presentation/views.py", "class View: pass\n")
        _write(
            tmp_path,
            "domain/model.py",
            "from presentation import View\n",
        )
        cfg = _cfg(arch_style="ddd")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1

    def test_mvc_models_cannot_import_views(self, tmp_path: Path) -> None:
        """models/ (rank 0) importing from views/ (rank 2) is a violation."""
        _write(tmp_path, "views/template.py", "class Template: pass\n")
        _write(
            tmp_path,
            "models/record.py",
            "from views import Template\n",
        )
        cfg = _cfg(arch_style="mvc")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1

    def test_unknown_arch_style_falls_back_to_layer_order(
        self, tmp_path: Path
    ) -> None:
        """An unrecognised arch_style falls back to layer_order without crashing."""
        _write(tmp_path, "services/svc.py", "class Svc: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "from services import Svc\n",
        )
        cfg = _cfg(
            arch_style="onion",  # not a recognised preset
            layer_order=["models", "services"],
        )
        failures = check_architecture(tmp_path, cfg)
        # Falls back to layer_order; violation should still be detected
        assert len(failures) >= 1

    def test_layered_preset_violation(self, tmp_path: Path) -> None:
        """models/ importing from api/ is a violation in the 'layered' preset."""
        _write(tmp_path, "api/routes.py", "class Router: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "from api import Router\n",
        )
        cfg = _cfg(arch_style="layered")
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1


# ===========================================================================
# layer_definitions — custom layer stacks
# ===========================================================================


class TestLayerDefinitions:
    def test_custom_definitions_detect_violation(self, tmp_path: Path) -> None:
        """Custom database→backend→frontend stack enforced correctly.

        In this custom stack database is innermost (rank 0). A file inside the
        database layer must not import from the outer frontend layer (rank 2).
        """
        _write(tmp_path, "frontend/ui.py", "class UI: pass\n")
        _write(
            tmp_path,
            "database/orm.py",
            "from frontend import UI\n",   # inner (rank 0) → outer (rank 2): violation
        )
        cfg = _cfg(layer_definitions=[
            {"name": "database", "rank": 0, "aliases": []},
            {"name": "backend",  "rank": 1, "aliases": []},
            {"name": "frontend", "rank": 2, "aliases": []},
        ])
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        assert any("database" in f.message for f in failures)

    def test_custom_definitions_allow_legal_import(self, tmp_path: Path) -> None:
        """frontend/ importing backend/ in the opposite direction is legal."""
        _write(tmp_path, "database/orm.py", "class ORM: pass\n")
        _write(
            tmp_path,
            "backend/service.py",
            "from database import ORM\n",
        )
        cfg = _cfg(layer_definitions=[
            {"name": "database", "rank": 0, "aliases": []},
            {"name": "backend",  "rank": 1, "aliases": []},
            {"name": "frontend", "rank": 2, "aliases": []},
        ])
        assert check_architecture(tmp_path, cfg) == []

    def test_aliases_in_layer_definitions_matched(self, tmp_path: Path) -> None:
        """Layer 'data' with alias 'persistence' matches a 'persistence/' dir."""
        _write(tmp_path, "logic/svc.py", "class Svc: pass\n")
        _write(
            tmp_path,
            "persistence/repo.py",   # should match alias of 'data'
            "from logic import Svc\n",
        )
        cfg = _cfg(layer_definitions=[
            {"name": "data",  "rank": 0, "aliases": ["persistence", "db"]},
            {"name": "logic", "rank": 1, "aliases": ["business", "services"]},
        ])
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1
        # Canonical name 'data' should appear in violation message
        assert any("data" in f.message for f in failures)

    def test_layer_definitions_priority_over_arch_style(
        self, tmp_path: Path
    ) -> None:
        """layer_definitions wins over arch_style when both are set."""
        # If arch_style="hexagonal" were used, 'domain'→'infrastructure' would
        # be a violation.  But our custom definitions have them reversed.
        _write(tmp_path, "infrastructure/infra.py", "class Infra: pass\n")
        _write(
            tmp_path,
            "domain/entity.py",
            "from infrastructure import Infra\n",
        )
        # Custom: infrastructure is rank 0 (inner), domain is rank 1 (outer)
        # → domain importing infrastructure is LEGAL under this custom stack
        cfg = _cfg(
            arch_style="hexagonal",
            layer_definitions=[
                {"name": "infrastructure", "rank": 0, "aliases": []},
                {"name": "domain",         "rank": 1, "aliases": []},
            ],
        )
        assert check_architecture(tmp_path, cfg) == []

    def test_empty_layer_definitions_falls_back_to_layer_order(
        self, tmp_path: Path
    ) -> None:
        """An empty layer_definitions list falls back to layer_order."""
        _write(tmp_path, "services/svc.py", "class Svc: pass\n")
        _write(
            tmp_path,
            "models/m.py",
            "from services import Svc\n",
        )
        cfg = _cfg(
            layer_order=["models", "services"],
            layer_definitions=[],   # empty → treated as not set
        )
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1

    def test_explicit_ranks_honoured(self, tmp_path: Path) -> None:
        """layer_definitions with non-sequential explicit ranks use those ranks."""
        # 'alpha' rank=10, 'beta' rank=20 — alpha cannot import beta
        _write(tmp_path, "beta/b.py", "class B: pass\n")
        _write(
            tmp_path,
            "alpha/a.py",
            "from beta import B\n",
        )
        cfg = _cfg(layer_definitions=[
            {"name": "beta",  "rank": 20, "aliases": []},
            {"name": "alpha", "rank": 10, "aliases": []},  # out-of-order in list
        ])
        failures = check_architecture(tmp_path, cfg)
        assert len(failures) >= 1

    def test_multiple_aliases_all_detected(self, tmp_path: Path) -> None:
        """All aliases for a layer are recognised, not just the first one."""
        # 'core', 'entities', and 'model' are all aliases for the inner layer
        for alias_dir in ("core", "entities"):
            _write(tmp_path, f"{alias_dir}/x.py", "class X: pass\n")
            _write(
                tmp_path,
                f"{alias_dir}/y.py",
                "from api import Router\n",
            )
        _write(tmp_path, "api/routes.py", "class Router: pass\n")
        cfg = _cfg(layer_definitions=[
            {"name": "inner", "rank": 0, "aliases": ["core", "entities", "model"]},
            {"name": "api",   "rank": 1, "aliases": ["routes", "controllers"]},
        ])
        failures = check_architecture(tmp_path, cfg)
        # Both core/ and entities/ files should produce violations
        assert len(failures) >= 2

    def test_non_dict_entries_in_layer_definitions_ignored(
        self, tmp_path: Path
    ) -> None:
        """Non-dict entries in layer_definitions are silently skipped."""
        _write(tmp_path, "models/m.py", "x = 1\n")
        cfg = _cfg(layer_definitions=[
            "invalid_string_entry",           # type: ignore[list-item]
            {"name": "models", "rank": 0, "aliases": []},
        ])
        # Should not crash
        result = check_architecture(tmp_path, cfg)
        assert isinstance(result, list)


# ===========================================================================
# ArchitectureGateConfig model
# ===========================================================================


class TestArchitectureGateConfigModel:
    def test_default_arch_style_is_none(self) -> None:
        cfg = ArchitectureGateConfig()
        assert cfg.arch_style is None

    def test_default_layer_definitions_is_none(self) -> None:
        cfg = ArchitectureGateConfig()
        assert cfg.layer_definitions is None

    def test_default_layer_order_present(self) -> None:
        cfg = ArchitectureGateConfig()
        assert cfg.layer_order == ["models", "repositories", "services", "api"]

    def test_model_dump_includes_arch_style(self) -> None:
        cfg = ArchitectureGateConfig(arch_style="ddd")
        d = cfg.model_dump()
        assert "arch_style" in d
        assert d["arch_style"] == "ddd"

    def test_model_dump_includes_layer_definitions(self) -> None:
        defs = [{"name": "core", "rank": 0, "aliases": []}]
        cfg = ArchitectureGateConfig(layer_definitions=defs)
        d = cfg.model_dump()
        assert "layer_definitions" in d
        assert d["layer_definitions"] == defs

    def test_model_validate_parses_arch_style(self) -> None:
        cfg = ArchitectureGateConfig.model_validate(
            {"arch_style": "hexagonal", "layer_order": ["a", "b"]}
        )
        assert cfg.arch_style == "hexagonal"

    def test_model_validate_parses_layer_definitions(self) -> None:
        defs = [{"name": "x", "rank": 0, "aliases": ["y"]}]
        cfg = ArchitectureGateConfig.model_validate({"layer_definitions": defs})
        assert cfg.layer_definitions == defs

    def test_model_validate_ignores_unknown_keys(self) -> None:
        # Should not raise
        cfg = ArchitectureGateConfig.model_validate(
            {"arch_style": "mvc", "nonexistent_key": True}
        )
        assert cfg.arch_style == "mvc"

    def test_backward_compat_no_new_fields(self) -> None:
        """Config without arch_style/layer_definitions still works."""
        cfg = ArchitectureGateConfig(layer_order=["models", "services"])
        assert cfg.arch_style is None
        assert cfg.layer_definitions is None
        assert cfg.layer_order == ["models", "services"]


# ===========================================================================
# ARCHITECTURE_STYLE_PRESETS
# ===========================================================================


class TestArchitectureStylePresets:
    _ALL_STYLES = ["layered", "clean", "hexagonal", "mvc", "ddd"]

    def test_all_expected_styles_present(self) -> None:
        for style in self._ALL_STYLES:
            assert style in ARCHITECTURE_STYLE_PRESETS, (
                f"Expected preset {style!r} missing from ARCHITECTURE_STYLE_PRESETS"
            )

    @pytest.mark.parametrize("style", _ALL_STYLES)
    def test_each_preset_is_sorted_by_rank(self, style: str) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS[style]
        ranks = [ld["rank"] for ld in layers]
        assert ranks == sorted(ranks), (
            f"Preset {style!r} layers are not sorted by rank: {ranks}"
        )

    @pytest.mark.parametrize("style", _ALL_STYLES)
    def test_each_layer_has_required_keys(self, style: str) -> None:
        for ld in ARCHITECTURE_STYLE_PRESETS[style]:
            assert "name" in ld
            assert "rank" in ld
            assert "aliases" in ld

    @pytest.mark.parametrize("style", _ALL_STYLES)
    def test_each_preset_has_at_least_two_layers(self, style: str) -> None:
        assert len(ARCHITECTURE_STYLE_PRESETS[style]) >= 2

    def test_hexagonal_innermost_layer_is_domain(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["hexagonal"]
        innermost = min(layers, key=lambda x: x["rank"])
        assert innermost["name"] == "domain"

    def test_clean_innermost_layer_is_entities(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["clean"]
        innermost = min(layers, key=lambda x: x["rank"])
        assert innermost["name"] == "entities"

    def test_ddd_innermost_layer_is_domain(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["ddd"]
        innermost = min(layers, key=lambda x: x["rank"])
        assert innermost["name"] == "domain"

    def test_mvc_innermost_layer_is_models(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["mvc"]
        innermost = min(layers, key=lambda x: x["rank"])
        assert innermost["name"] == "models"

    def test_layered_innermost_layer_is_models(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["layered"]
        innermost = min(layers, key=lambda x: x["rank"])
        assert innermost["name"] == "models"

    def test_hexagonal_has_core_alias_for_domain(self) -> None:
        hexagonal = ARCHITECTURE_STYLE_PRESETS["hexagonal"]
        domain_layer = next(ld for ld in hexagonal if ld["name"] == "domain")
        assert "core" in domain_layer["aliases"]

    def test_ddd_presentation_is_outermost(self) -> None:
        layers = ARCHITECTURE_STYLE_PRESETS["ddd"]
        outermost = max(layers, key=lambda x: x["rank"])
        assert outermost["name"] == "presentation"


# ===========================================================================
# _resolve_layer_definitions
# ===========================================================================


class TestResolveLayerDefinitions:
    def test_plain_layer_order_returned_by_default(self) -> None:
        cfg = _cfg(layer_order=["models", "services", "api"])
        result = _resolve_layer_definitions(cfg)
        assert [ld["name"] for ld in result] == ["models", "services", "api"]
        assert all(ld["rank"] == i for i, ld in enumerate(result))
        assert all(ld["aliases"] == [] for ld in result)

    def test_arch_style_returns_preset(self) -> None:
        cfg = _cfg(arch_style="hexagonal")
        result = _resolve_layer_definitions(cfg)
        names = [ld["name"] for ld in result]
        assert "domain" in names
        assert "infrastructure" in names

    def test_layer_definitions_returns_normalised_dicts(self) -> None:
        raw = [
            {"name": "core",  "rank": 0, "aliases": ["domain"]},
            {"name": "shell", "rank": 1, "aliases": []},
        ]
        cfg = _cfg(layer_definitions=raw)
        result = _resolve_layer_definitions(cfg)
        assert result[0]["name"] == "core"
        assert result[0]["aliases"] == ["domain"]
        assert result[1]["name"] == "shell"

    def test_layer_definitions_sorted_by_rank(self) -> None:
        raw = [
            {"name": "outer", "rank": 5, "aliases": []},
            {"name": "inner", "rank": 1, "aliases": []},
        ]
        cfg = _cfg(layer_definitions=raw)
        result = _resolve_layer_definitions(cfg)
        assert result[0]["name"] == "inner"
        assert result[1]["name"] == "outer"

    def test_layer_definitions_priority_over_arch_style(self) -> None:
        custom = [{"name": "myinner", "rank": 0, "aliases": []}]
        cfg = _cfg(arch_style="hexagonal", layer_definitions=custom)
        result = _resolve_layer_definitions(cfg)
        assert len(result) == 1
        assert result[0]["name"] == "myinner"

    def test_unknown_arch_style_falls_back_to_layer_order(self) -> None:
        cfg = _cfg(arch_style="unknown_style", layer_order=["a", "b"])
        result = _resolve_layer_definitions(cfg)
        assert [ld["name"] for ld in result] == ["a", "b"]

    def test_empty_layer_definitions_falls_back_to_layer_order(self) -> None:
        cfg = _cfg(layer_definitions=[], layer_order=["x", "y"])
        result = _resolve_layer_definitions(cfg)
        assert [ld["name"] for ld in result] == ["x", "y"]

    def test_result_always_has_required_keys(self) -> None:
        for cfg in [
            _cfg(layer_order=["a", "b"]),
            _cfg(arch_style="mvc"),
            _cfg(layer_definitions=[{"name": "z", "rank": 0, "aliases": []}]),
        ]:
            for ld in _resolve_layer_definitions(cfg):
                assert "name" in ld
                assert "rank" in ld
                assert "aliases" in ld


# ===========================================================================
# _render_architecture (config generator)
# ===========================================================================


class TestRenderArchitecture:
    # ── Existing assertions (backward compat) ───────────────────────────────

    def test_rules_listed(self) -> None:
        cfg = ArchitectureGateConfig(rules=["no_circular_dependencies"])
        out = _render_architecture(cfg)
        assert "no_circular_dependencies" in out

    def test_layer_order_present_when_no_style_or_defs(self) -> None:
        cfg = ArchitectureGateConfig(layer_order=["domain", "api"])
        out = _render_architecture(cfg)
        assert "domain" in out
        assert "api" in out

    def test_report_only_false_present(self) -> None:
        cfg = ArchitectureGateConfig(report_only=False)
        out = _render_architecture(cfg)
        assert "report_only: false" in out

    def test_architecture_label_present(self) -> None:
        out = _render_architecture(ArchitectureGateConfig())
        assert "architecture:" in out

    # ── New arch_style field ─────────────────────────────────────────────────

    def test_arch_style_emitted_when_set(self) -> None:
        cfg = ArchitectureGateConfig(arch_style="hexagonal")
        out = _render_architecture(cfg)
        assert "arch_style: hexagonal" in out

    def test_layer_order_not_emitted_when_arch_style_set(self) -> None:
        cfg = ArchitectureGateConfig(arch_style="clean")
        out = _render_architecture(cfg)
        assert "layer_order:" not in out

    def test_arch_style_ddd_in_output(self) -> None:
        cfg = ArchitectureGateConfig(arch_style="ddd")
        out = _render_architecture(cfg)
        assert "ddd" in out

    # ── New layer_definitions field ──────────────────────────────────────────

    def test_layer_definitions_block_emitted(self) -> None:
        cfg = ArchitectureGateConfig(layer_definitions=[
            {"name": "core", "rank": 0, "aliases": ["domain"]},
            {"name": "api",  "rank": 1, "aliases": []},
        ])
        out = _render_architecture(cfg)
        assert "layer_definitions:" in out
        assert "core" in out
        assert "domain" in out

    def test_layer_definitions_aliases_in_output(self) -> None:
        cfg = ArchitectureGateConfig(layer_definitions=[
            {"name": "data", "rank": 0, "aliases": ["persistence", "db"]},
        ])
        out = _render_architecture(cfg)
        assert "persistence" in out
        assert "db" in out

    def test_layer_definitions_priority_over_arch_style_in_render(self) -> None:
        """When both are set, layer_definitions block is emitted (not arch_style)."""
        cfg = ArchitectureGateConfig(
            arch_style="hexagonal",
            layer_definitions=[{"name": "custom", "rank": 0, "aliases": []}],
        )
        out = _render_architecture(cfg)
        assert "layer_definitions:" in out
        assert "arch_style:" not in out

    def test_report_only_always_emitted(self) -> None:
        """report_only appears regardless of which layer config method is used."""
        for cfg in [
            ArchitectureGateConfig(arch_style="mvc"),
            ArchitectureGateConfig(layer_definitions=[{"name": "x", "rank": 0, "aliases": []}]),
            ArchitectureGateConfig(layer_order=["a", "b"]),
        ]:
            out = _render_architecture(cfg)
            assert "report_only:" in out
