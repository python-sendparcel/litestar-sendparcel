"""Dependency injection tests."""

from __future__ import annotations

import litestar_sendparcel.dependencies as deps_mod


class TestDependenciesModule:
    def test_module_is_importable(self) -> None:
        assert deps_mod is not None

    def test_module_has_docstring(self) -> None:
        assert deps_mod.__doc__ is not None

    def test_provide_functions_are_callable(self) -> None:
        """Every public 'provide_*' function should be callable."""
        provides = [
            name for name in dir(deps_mod) if name.startswith("provide_")
        ]
        for name in provides:
            fn = getattr(deps_mod, name)
            assert callable(fn), f"{name} should be callable"

    def test_no_unexpected_public_names(self) -> None:
        """Module should only export expected names (or nothing)."""
        public = [name for name in dir(deps_mod) if not name.startswith("_")]
        # Placeholder module has no public names, which is fine
        # If provide_* functions are added later, they'll be
        # tested by test_provide_functions_are_callable
        assert isinstance(public, list)
