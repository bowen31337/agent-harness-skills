"""
tests/test_architecture.py
===========================
Structural test suite — validates all architectural invariants for the
harness-skills codebase without relying on runtime behaviour.

Every test in this module checks a *static* property of the package:
imports, ``__all__`` declarations, dataclass fields, and inter-package
dependency direction.  Running any individual test is safe; the suite
never mutates the file system or executes gate logic.

Invariants covered
------------------
1. **Domain package completeness** — every declared domain package has a
   valid, parseable ``__init__.py`` that declares ``__all__``.

2. **Package boundary correctness** — ``__all__`` in every package contains
   only public symbols; every exported symbol is importable from the
   package root.

3. **Layer dependency ordering** — at the ``__init__.py`` level the
   dependency graph respects the documented layer order::

       models ◄── plugins ◄── gates ◄── generators ◄── cli

   Inner-layer packages must not import from outer-layer packages.

4. **Circular-dependency freedom** — the directed graph built from each
   sub-package's ``__init__.py`` is acyclic.

5. **Standalone package isolation** — ``dom_snapshot_utility``,
   ``harness_dashboard``, and ``log_format_linter`` must not import from
   ``harness_skills`` in their ``__init__.py``.

6. **Gate config registry completeness** — ``GATE_CONFIG_CLASSES`` must
   register exactly the nine documented gate IDs, each mapped to a
   ``BaseGateConfig`` subclass with both ``enabled`` and
   ``fail_on_error`` dataclass fields.

7. **Profile defaults completeness** — ``PROFILE_GATE_DEFAULTS`` must
   define all three profiles (``starter``, ``standard``, ``advanced``),
   each supplying a correctly-typed config object for every registered gate.

8. **``BaseGateConfig`` shims** — ``model_dump`` / ``model_validate`` must
   round-trip without data loss for every registered gate config class.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Absolute path to the repository root (parent of the ``tests/`` directory).
ROOT: Path = Path(__file__).resolve().parent.parent


def _collect_imports(init_py: Path) -> list[str]:
    """Return the flat list of module names referenced by every ``import`` /
    ``from … import`` statement in *init_py* (top-level statements only).

    Relative imports (e.g. ``from .snapshot import …``) contribute only the
    bare dotted suffix (e.g. ``"snapshot"``), which will never match an
    absolute package name, so they do not affect layer-boundary checks.
    """
    source = init_py.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(init_py))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                # absolute import — include the full dotted module name
                imported.append(node.module)
    return imported


def _imports_any(init_py: Path, prefixes: list[str]) -> list[str]:
    """Return imported module names from *init_py* whose dotted path starts
    with any of *prefixes* or equals a prefix exactly."""
    hits: list[str] = []
    for module in _collect_imports(init_py):
        for prefix in prefixes:
            if module == prefix or module.startswith(prefix + "."):
                hits.append(module)
                break
    return hits


def _has_all_declaration(tree: ast.AST) -> bool:
    """Return ``True`` if *tree* contains any top-level ``__all__``
    declaration (plain assignment *or* annotated assignment)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__all__":
                return True
    return False


def _subpkg_init(subpkg: str) -> Path:
    """Return the absolute path to ``harness_skills/<subpkg>/__init__.py``."""
    return ROOT / "harness_skills" / subpkg / "__init__.py"


# ---------------------------------------------------------------------------
# 1. Domain package completeness
# ---------------------------------------------------------------------------


class TestDomainPackageCompleteness:
    """Every declared domain package must have a valid, parseable
    ``__init__.py`` that contains an ``__all__`` declaration."""

    _INIT_FILES: list[Path] = [
        ROOT / "harness_skills" / "__init__.py",
        ROOT / "harness_skills" / "models" / "__init__.py",
        ROOT / "harness_skills" / "gates" / "__init__.py",
        ROOT / "harness_skills" / "generators" / "__init__.py",
        ROOT / "harness_skills" / "plugins" / "__init__.py",
        ROOT / "harness_skills" / "cli" / "__init__.py",
        ROOT / "harness_skills" / "utils" / "__init__.py",
        ROOT / "dom_snapshot_utility" / "__init__.py",
        ROOT / "harness_dashboard" / "__init__.py",
        ROOT / "log_format_linter" / "__init__.py",
    ]

    _IDS: list[str] = [str(p.relative_to(ROOT)) for p in _INIT_FILES]

    @pytest.mark.parametrize("init_path", _INIT_FILES, ids=_IDS)
    def test_init_file_exists(self, init_path: Path) -> None:
        """Every declared domain package must have an ``__init__.py``."""
        assert init_path.exists(), (
            f"Missing package init file: {init_path.relative_to(ROOT)}"
        )

    @pytest.mark.parametrize("init_path", _INIT_FILES, ids=_IDS)
    def test_init_file_is_valid_python(self, init_path: Path) -> None:
        """Every ``__init__.py`` must parse without ``SyntaxError``."""
        source = init_path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(init_path))
        except SyntaxError as exc:
            pytest.fail(
                f"{init_path.relative_to(ROOT)} contains a syntax error: {exc}"
            )

    @pytest.mark.parametrize("init_path", _INIT_FILES, ids=_IDS)
    def test_init_declares_all(self, init_path: Path) -> None:
        """Every ``__init__.py`` must declare ``__all__``."""
        source = init_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(init_path))
        assert _has_all_declaration(tree), (
            f"{init_path.relative_to(ROOT)} does not declare __all__"
        )


# ---------------------------------------------------------------------------
# 2. Package boundary correctness
# ---------------------------------------------------------------------------


class TestPackageBoundaries:
    """``__all__`` must list only public symbols; every listed symbol must be
    importable from the package root."""

    _PACKAGES: list[str] = [
        "harness_skills",
        "harness_skills.models",
        "harness_skills.gates",
        "harness_skills.generators",
        "harness_skills.plugins",
        "harness_skills.cli",
        "harness_skills.utils",
        "dom_snapshot_utility",
        "harness_dashboard",
        "log_format_linter",
    ]

    @pytest.mark.parametrize("pkg_name", _PACKAGES)
    def test_all_is_list_or_tuple(self, pkg_name: str) -> None:
        """``__all__`` must be a ``list`` or ``tuple``, not another type."""
        mod = importlib.import_module(pkg_name)
        assert hasattr(mod, "__all__"), (
            f"{pkg_name}: __all__ is not declared"
        )
        assert isinstance(mod.__all__, (list, tuple)), (
            f"{pkg_name}.__all__ must be list or tuple, "
            f"got {type(mod.__all__).__name__}"
        )

    @pytest.mark.parametrize("pkg_name", _PACKAGES)
    def test_no_private_symbols_in_all(self, pkg_name: str) -> None:
        """``__all__`` must not contain any ``_``-prefixed (private) names."""
        mod = importlib.import_module(pkg_name)
        if not hasattr(mod, "__all__"):
            pytest.skip(f"{pkg_name} has no __all__")
        private = [s for s in mod.__all__ if s.startswith("_")]
        assert not private, (
            f"{pkg_name}.__all__ contains private symbols: {private}"
        )

    @pytest.mark.parametrize("pkg_name", _PACKAGES)
    def test_all_exported_symbols_are_importable(self, pkg_name: str) -> None:
        """Every symbol in ``__all__`` must be accessible as an attribute of
        the package module (i.e. ``from <pkg> import <symbol>`` must work)."""
        mod = importlib.import_module(pkg_name)
        if not hasattr(mod, "__all__"):
            pytest.skip(f"{pkg_name} has no __all__")
        missing = [s for s in mod.__all__ if not hasattr(mod, s)]
        assert not missing, (
            f"{pkg_name}.__all__ lists symbols not accessible from the "
            f"package root: {missing}"
        )

    @pytest.mark.parametrize("pkg_name", _PACKAGES)
    def test_all_entries_are_strings(self, pkg_name: str) -> None:
        """Every entry in ``__all__`` must be a plain string."""
        mod = importlib.import_module(pkg_name)
        if not hasattr(mod, "__all__"):
            pytest.skip(f"{pkg_name} has no __all__")
        non_strings = [
            (i, type(s).__name__)
            for i, s in enumerate(mod.__all__)
            if not isinstance(s, str)
        ]
        assert not non_strings, (
            f"{pkg_name}.__all__ contains non-string entries at positions: "
            f"{non_strings}"
        )


# ---------------------------------------------------------------------------
# 3. Layer dependency ordering (checked via AST on __init__.py only)
# ---------------------------------------------------------------------------


class TestLayerDependencies:
    """Documented layer order::

        models ◄── plugins ◄── gates ◄── generators ◄── cli

    An inner-layer package's ``__init__.py`` must not contain absolute imports
    from an outer-layer package.  (Implementation modules may have additional
    cross-layer imports documented as open violations in ARCHITECTURE.md; only
    the *public* ``__init__.py`` boundary is enforced here.)
    """

    _HS: str = "harness_skills"

    # ── models must not import from any other harness_skills sub-package ──

    def test_models_does_not_import_from_gates(self) -> None:
        hits = _imports_any(_subpkg_init("models"), [f"{self._HS}.gates"])
        assert not hits, (
            f"harness_skills/models/__init__.py must not import from "
            f"harness_skills.gates; found: {hits}"
        )

    def test_models_does_not_import_from_generators(self) -> None:
        hits = _imports_any(_subpkg_init("models"), [f"{self._HS}.generators"])
        assert not hits, (
            f"harness_skills/models/__init__.py must not import from "
            f"harness_skills.generators; found: {hits}"
        )

    def test_models_does_not_import_from_cli(self) -> None:
        hits = _imports_any(_subpkg_init("models"), [f"{self._HS}.cli"])
        assert not hits, (
            f"harness_skills/models/__init__.py must not import from "
            f"harness_skills.cli; found: {hits}"
        )

    def test_models_does_not_import_from_plugins(self) -> None:
        hits = _imports_any(_subpkg_init("models"), [f"{self._HS}.plugins"])
        assert not hits, (
            f"harness_skills/models/__init__.py must not import from "
            f"harness_skills.plugins; found: {hits}"
        )

    # ── plugins must not import from gates, generators, or cli ──

    def test_plugins_does_not_import_from_gates(self) -> None:
        hits = _imports_any(_subpkg_init("plugins"), [f"{self._HS}.gates"])
        assert not hits, (
            f"harness_skills/plugins/__init__.py must not import from "
            f"harness_skills.gates; found: {hits}"
        )

    def test_plugins_does_not_import_from_generators(self) -> None:
        hits = _imports_any(_subpkg_init("plugins"), [f"{self._HS}.generators"])
        assert not hits, (
            f"harness_skills/plugins/__init__.py must not import from "
            f"harness_skills.generators; found: {hits}"
        )

    def test_plugins_does_not_import_from_cli(self) -> None:
        hits = _imports_any(_subpkg_init("plugins"), [f"{self._HS}.cli"])
        assert not hits, (
            f"harness_skills/plugins/__init__.py must not import from "
            f"harness_skills.cli; found: {hits}"
        )

    # ── gates must not import from generators or cli ──

    def test_gates_does_not_import_from_generators(self) -> None:
        hits = _imports_any(_subpkg_init("gates"), [f"{self._HS}.generators"])
        assert not hits, (
            f"harness_skills/gates/__init__.py must not import from "
            f"harness_skills.generators; found: {hits}"
        )

    def test_gates_does_not_import_from_cli(self) -> None:
        hits = _imports_any(_subpkg_init("gates"), [f"{self._HS}.cli"])
        assert not hits, (
            f"harness_skills/gates/__init__.py must not import from "
            f"harness_skills.cli; found: {hits}"
        )

    # ── generators must not import from cli ──

    def test_generators_does_not_import_from_cli(self) -> None:
        hits = _imports_any(_subpkg_init("generators"), [f"{self._HS}.cli"])
        assert not hits, (
            f"harness_skills/generators/__init__.py must not import from "
            f"harness_skills.cli; found: {hits}"
        )


# ---------------------------------------------------------------------------
# 4. Circular-dependency freedom
# ---------------------------------------------------------------------------


class TestNoCycles:
    """The directed graph built from each sub-package's ``__init__.py``
    (edges = absolute imports of other harness_skills sub-packages) must be
    a DAG — no cycles allowed."""

    _SUBPKGS: list[str] = [
        "models", "plugins", "gates", "generators", "cli", "utils",
    ]

    def _build_adjacency(self) -> dict[str, set[str]]:
        """Build directed adjacency map: sub-package → set[sub-packages it
        imports in its ``__init__.py``]."""
        hs_prefix = "harness_skills."
        adj: dict[str, set[str]] = {pkg: set() for pkg in self._SUBPKGS}
        for pkg in self._SUBPKGS:
            init_py = _subpkg_init(pkg)
            for module in _collect_imports(init_py):
                if not module.startswith(hs_prefix):
                    continue
                rest = module[len(hs_prefix):]   # e.g. "models.base" or "cli"
                sub = rest.split(".")[0]          # first segment only
                if sub in adj and sub != pkg:
                    adj[pkg].add(sub)
        return adj

    def test_subpackage_import_graph_is_acyclic(self) -> None:
        """DFS over the adjacency map must find no back-edges."""
        adj = self._build_adjacency()
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def _dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbour in adj.get(node, set()):
                if neighbour not in visited:
                    if _dfs(neighbour):
                        return True
                elif neighbour in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        cycle_roots = [p for p in adj if p not in visited and _dfs(p)]
        assert not cycle_roots, (
            f"Circular dependency detected among harness_skills sub-packages. "
            f"Adjacency map: {adj}"
        )

    def test_models_has_no_outer_layer_deps(self) -> None:
        """``models`` is the innermost layer — its ``__init__.py`` must not
        depend on any other harness_skills sub-package."""
        adj = self._build_adjacency()
        other_subpkgs = set(self._SUBPKGS) - {"models"}
        bad = adj.get("models", set()) & other_subpkgs
        assert not bad, (
            f"harness_skills/models/__init__.py imports from outer-layer "
            f"sub-packages: {sorted(bad)}"
        )


# ---------------------------------------------------------------------------
# 5. Standalone package isolation
# ---------------------------------------------------------------------------


class TestStandalonePackageIsolation:
    """Standalone packages must not import from ``harness_skills`` in their
    public ``__init__.py`` (they are declared as having no local
    dependencies in ARCHITECTURE.md)."""

    _STANDALONES: list[tuple[str, Path]] = [
        ("dom_snapshot_utility", ROOT / "dom_snapshot_utility" / "__init__.py"),
        ("harness_dashboard",    ROOT / "harness_dashboard"    / "__init__.py"),
        ("log_format_linter",    ROOT / "log_format_linter"    / "__init__.py"),
    ]

    @pytest.mark.parametrize(
        "pkg_name,init_py",
        _STANDALONES,
        ids=[t[0] for t in _STANDALONES],
    )
    def test_does_not_import_harness_skills(
        self, pkg_name: str, init_py: Path
    ) -> None:
        """Standalone package ``__init__.py`` must not reference
        ``harness_skills``."""
        hits = _imports_any(init_py, ["harness_skills"])
        assert not hits, (
            f"{pkg_name}/__init__.py imports from harness_skills: {hits}"
        )

    @pytest.mark.parametrize(
        "pkg_name,init_py",
        _STANDALONES,
        ids=[t[0] for t in _STANDALONES],
    )
    def test_does_not_import_other_standalone_packages(
        self, pkg_name: str, init_py: Path
    ) -> None:
        """Standalone packages must not import each other."""
        other_standalones = [
            name for name, _ in self._STANDALONES if name != pkg_name
        ]
        hits = _imports_any(init_py, other_standalones)
        assert not hits, (
            f"{pkg_name}/__init__.py imports from another standalone package: "
            f"{hits}"
        )


# ---------------------------------------------------------------------------
# 6. Gate config registry completeness
# ---------------------------------------------------------------------------

_EXPECTED_GATES: frozenset[str] = frozenset({
    "regression",
    "coverage",
    "security",
    "performance",
    "architecture",
    "principles",
    "docs_freshness",
    "types",
    "lint",
    "agents_md_token",
    "file_size",
})


class TestGateConfigRegistry:
    """``GATE_CONFIG_CLASSES`` must be exhaustive, well-typed, and internally
    consistent."""

    def _registry(self) -> dict[str, type]:
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        return GATE_CONFIG_CLASSES  # type: ignore[return-value]

    def _base(self) -> type:
        from harness_skills.models.gate_configs import BaseGateConfig
        return BaseGateConfig

    # ── registry membership ──────────────────────────────────────────────

    def test_all_expected_gates_are_registered(self) -> None:
        """Every documented gate ID must appear in ``GATE_CONFIG_CLASSES``."""
        missing = _EXPECTED_GATES - set(self._registry())
        assert not missing, (
            f"GATE_CONFIG_CLASSES is missing gate IDs: {sorted(missing)}"
        )

    def test_no_undocumented_gates_registered(self) -> None:
        """``GATE_CONFIG_CLASSES`` must not contain gate IDs beyond the nine
        documented ones."""
        extra = set(self._registry()) - _EXPECTED_GATES
        assert not extra, (
            f"GATE_CONFIG_CLASSES contains undocumented gate IDs: "
            f"{sorted(extra)}"
        )

    # ── per-gate class invariants ────────────────────────────────────────

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_is_dataclass(self, gate_id: str) -> None:
        """Every registered gate config class must be a ``@dataclass``."""
        cls = self._registry()[gate_id]
        assert dataclasses.is_dataclass(cls), (
            f"{gate_id}: {cls.__name__} must be decorated with @dataclass"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_inherits_base(self, gate_id: str) -> None:
        """Every registered class must be a ``BaseGateConfig`` subclass."""
        cls = self._registry()[gate_id]
        assert issubclass(cls, self._base()), (
            f"{gate_id}: {cls.__name__} must inherit from BaseGateConfig"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_has_enabled_field(self, gate_id: str) -> None:
        """Every gate config must declare an ``enabled`` dataclass field."""
        cls = self._registry()[gate_id]
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert "enabled" in field_names, (
            f"{gate_id}: {cls.__name__} is missing the 'enabled' field"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_has_fail_on_error_field(self, gate_id: str) -> None:
        """Every gate config must declare a ``fail_on_error`` dataclass field."""
        cls = self._registry()[gate_id]
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert "fail_on_error" in field_names, (
            f"{gate_id}: {cls.__name__} is missing the 'fail_on_error' field"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_instantiates_with_no_args(self, gate_id: str) -> None:
        """Every gate config class must be instantiable with no arguments
        (all fields must have defaults)."""
        cls = self._registry()[gate_id]
        instance = cls()
        assert isinstance(instance, cls)

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_enabled_field_is_bool(self, gate_id: str) -> None:
        """The default value of ``enabled`` must be a bool."""
        cls = self._registry()[gate_id]
        instance = cls()
        assert isinstance(instance.enabled, bool), (
            f"{gate_id}: {cls.__name__}.enabled default must be bool, "
            f"got {type(instance.enabled).__name__}"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_gate_config_fail_on_error_field_is_bool(self, gate_id: str) -> None:
        """The default value of ``fail_on_error`` must be a bool."""
        cls = self._registry()[gate_id]
        instance = cls()
        assert isinstance(instance.fail_on_error, bool), (
            f"{gate_id}: {cls.__name__}.fail_on_error default must be bool, "
            f"got {type(instance.fail_on_error).__name__}"
        )

    # ── registry type check ──────────────────────────────────────────────

    def test_registry_maps_strings_to_classes(self) -> None:
        """``GATE_CONFIG_CLASSES`` must be a ``dict`` mapping ``str`` → ``type``."""
        registry = self._registry()
        assert isinstance(registry, dict), (
            f"GATE_CONFIG_CLASSES must be a dict, got {type(registry).__name__}"
        )
        for key, val in registry.items():
            assert isinstance(key, str), (
                f"GATE_CONFIG_CLASSES key {key!r} is not a str"
            )
            assert isinstance(val, type), (
                f"GATE_CONFIG_CLASSES[{key!r}] is not a type, "
                f"got {type(val).__name__}"
            )


# ---------------------------------------------------------------------------
# 7. Profile defaults completeness
# ---------------------------------------------------------------------------

_EXPECTED_PROFILES: frozenset[str] = frozenset({"starter", "standard", "advanced"})


class TestProfileDefaults:
    """``PROFILE_GATE_DEFAULTS`` must define exactly three profiles, each with
    a correctly-typed config object for every registered gate."""

    def _defaults(self) -> dict[str, Any]:
        from harness_skills.models.gate_configs import PROFILE_GATE_DEFAULTS
        return PROFILE_GATE_DEFAULTS

    def _registry(self) -> dict[str, type]:
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        return GATE_CONFIG_CLASSES  # type: ignore[return-value]

    # ── profile membership ───────────────────────────────────────────────

    def test_all_expected_profiles_present(self) -> None:
        """``PROFILE_GATE_DEFAULTS`` must define all three profiles."""
        missing = _EXPECTED_PROFILES - set(self._defaults())
        assert not missing, (
            f"PROFILE_GATE_DEFAULTS is missing profiles: {sorted(missing)}"
        )

    def test_no_undocumented_profiles(self) -> None:
        """``PROFILE_GATE_DEFAULTS`` must not contain undocumented profiles."""
        extra = set(self._defaults()) - _EXPECTED_PROFILES
        assert not extra, (
            f"PROFILE_GATE_DEFAULTS contains undocumented profiles: "
            f"{sorted(extra)}"
        )

    # ── per-profile gate coverage ────────────────────────────────────────

    @pytest.mark.parametrize("profile", sorted(_EXPECTED_PROFILES))
    def test_profile_defines_all_gates(self, profile: str) -> None:
        """Each profile must supply an entry for every registered gate ID."""
        profile_gates = set(self._defaults().get(profile, {}))
        missing = _EXPECTED_GATES - profile_gates
        assert not missing, (
            f"Profile '{profile}' is missing gate entries: {sorted(missing)}"
        )

    @pytest.mark.parametrize("profile", sorted(_EXPECTED_PROFILES))
    def test_profile_defines_no_extra_gates(self, profile: str) -> None:
        """A profile must not define gate IDs beyond the nine registered ones."""
        profile_gates = set(self._defaults().get(profile, {}))
        extra = profile_gates - _EXPECTED_GATES
        assert not extra, (
            f"Profile '{profile}' has entries for undocumented gate IDs: "
            f"{sorted(extra)}"
        )

    @pytest.mark.parametrize("profile", sorted(_EXPECTED_PROFILES))
    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_profile_gate_entry_is_correct_type(
        self, profile: str, gate_id: str
    ) -> None:
        """Each gate entry in a profile must be an instance of the class
        registered for that gate ID in ``GATE_CONFIG_CLASSES``."""
        profile_data = self._defaults().get(profile, {})
        if gate_id not in profile_data:
            pytest.skip(
                f"Profile '{profile}' has no entry for gate '{gate_id}'"
            )
        entry = profile_data[gate_id]
        expected_cls = self._registry()[gate_id]
        assert isinstance(entry, expected_cls), (
            f"Profile '{profile}' gate '{gate_id}': expected instance of "
            f"{expected_cls.__name__}, got {type(entry).__name__}"
        )

    @pytest.mark.parametrize("profile", sorted(_EXPECTED_PROFILES))
    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_profile_gate_entry_is_base_subclass_instance(
        self, profile: str, gate_id: str
    ) -> None:
        """Every profile gate entry must be a ``BaseGateConfig`` instance."""
        from harness_skills.models.gate_configs import BaseGateConfig
        profile_data = self._defaults().get(profile, {})
        if gate_id not in profile_data:
            pytest.skip(
                f"Profile '{profile}' has no entry for gate '{gate_id}'"
            )
        entry = profile_data[gate_id]
        assert isinstance(entry, BaseGateConfig), (
            f"Profile '{profile}' gate '{gate_id}': entry is not a "
            f"BaseGateConfig instance (got {type(entry).__name__})"
        )


# ---------------------------------------------------------------------------
# 8. BaseGateConfig shims
# ---------------------------------------------------------------------------


class TestBaseGateConfigShims:
    """``model_dump`` / ``model_validate`` must round-trip correctly for every
    registered gate config class."""

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_dump_returns_dict(self, gate_id: str) -> None:
        """``model_dump()`` must return a ``dict``."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        instance = GATE_CONFIG_CLASSES[gate_id]()
        result = instance.model_dump()
        assert isinstance(result, dict), (
            f"{gate_id}: model_dump() returned {type(result).__name__}, "
            f"expected dict"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_dump_contains_enabled(self, gate_id: str) -> None:
        """``model_dump()`` dict must include the ``enabled`` key."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        d = GATE_CONFIG_CLASSES[gate_id]().model_dump()
        assert "enabled" in d, (
            f"{gate_id}: model_dump() is missing the 'enabled' key"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_dump_contains_fail_on_error(self, gate_id: str) -> None:
        """``model_dump()`` dict must include the ``fail_on_error`` key."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        d = GATE_CONFIG_CLASSES[gate_id]().model_dump()
        assert "fail_on_error" in d, (
            f"{gate_id}: model_dump() is missing the 'fail_on_error' key"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_dump_values_match_instance_fields(self, gate_id: str) -> None:
        """Values in ``model_dump()`` must match the instance's dataclass
        field values exactly."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        cls = GATE_CONFIG_CLASSES[gate_id]
        instance = cls()
        d = instance.model_dump()
        expected = dataclasses.asdict(instance)
        assert d == expected, (
            f"{gate_id}: model_dump() returned {d!r}, "
            f"expected {expected!r}"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_validate_round_trips(self, gate_id: str) -> None:
        """``model_validate(model_dump())`` must reproduce an equal instance."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        cls = GATE_CONFIG_CLASSES[gate_id]
        original = cls()
        restored = cls.model_validate(original.model_dump())
        assert dataclasses.asdict(restored) == dataclasses.asdict(original), (
            f"{gate_id}: model_validate(model_dump()) did not round-trip; "
            f"got {dataclasses.asdict(restored)!r}"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_validate_returns_correct_type(self, gate_id: str) -> None:
        """``model_validate`` must return an instance of the calling class."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        cls = GATE_CONFIG_CLASSES[gate_id]
        instance = cls.model_validate({})
        assert isinstance(instance, cls), (
            f"{gate_id}: model_validate({{}}) returned "
            f"{type(instance).__name__}, expected {cls.__name__}"
        )

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_validate_ignores_unknown_keys(self, gate_id: str) -> None:
        """``model_validate`` must silently drop keys not in the dataclass
        (forward-compatibility with newer harness.config.yaml schemas)."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        cls = GATE_CONFIG_CLASSES[gate_id]
        # Include a key that will never be a real field name
        data = {"enabled": True, "fail_on_error": False, "__xunknown__": "drop"}
        try:
            instance = cls.model_validate(data)
        except TypeError as exc:
            pytest.fail(
                f"{gate_id}: model_validate raised TypeError on unknown key — "
                f"forward-compatibility is broken: {exc}"
            )
        assert isinstance(instance, cls)

    @pytest.mark.parametrize("gate_id", sorted(_EXPECTED_GATES))
    def test_model_validate_respects_provided_values(self, gate_id: str) -> None:
        """``model_validate`` must use the ``enabled`` value from the input
        dict rather than always returning the default."""
        from harness_skills.models.gate_configs import GATE_CONFIG_CLASSES
        cls = GATE_CONFIG_CLASSES[gate_id]
        # Toggle enabled — at least one of True/False differs from some default
        for enabled_val in (True, False):
            instance = cls.model_validate({"enabled": enabled_val})
            assert instance.enabled == enabled_val, (
                f"{gate_id}: model_validate({{'enabled': {enabled_val}}}) "
                f"returned enabled={instance.enabled}"
            )
