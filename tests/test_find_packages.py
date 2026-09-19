# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from pathlib import Path

from jupyter_builder.federated_extensions import (
    _find_namespace_packages,
    _find_packages,
    _valid_package_dirs,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_valid_package_dirs_keeps_only_identifier_non_vendored_dirs():
    dirs = ["pkg", "node_modules", "__pycache__", "venv", "env", "ui-tests", ".hidden", "1bad"]
    assert _valid_package_dirs(dirs) == ["pkg"]


def test_find_packages_requires_init_py(tmp_path):
    _touch(tmp_path / "pkg" / "__init__.py")
    _touch(tmp_path / "pkg" / "sub" / "__init__.py")
    # A dir without __init__.py is not a package and must be ignored.
    _touch(tmp_path / "not_a_pkg" / "module.py")

    assert sorted(_find_packages(str(tmp_path))) == ["pkg", "pkg.sub"]


def test_find_packages_does_not_descend_into_non_package_parents(tmp_path):
    # `inner` has an __init__.py but its parent `outer` does not, so it must
    # not be reported (matches setuptools.find_packages semantics).
    _touch(tmp_path / "outer" / "inner" / "__init__.py")

    assert _find_packages(str(tmp_path)) == []


def test_find_packages_skips_node_modules(tmp_path):
    _touch(tmp_path / "pkg" / "__init__.py")
    # Even if a node_modules subtree contains __init__.py files, it is skipped.
    _touch(tmp_path / "node_modules" / "flatted" / "__init__.py")
    _touch(tmp_path / "node_modules" / "flatted" / "python" / "__init__.py")

    assert _find_packages(str(tmp_path)) == ["pkg"]


def test_find_namespace_packages_finds_dirs_without_init_py(tmp_path):
    # No __init__.py anywhere: still discovered as namespace packages.
    _touch(tmp_path / "ns_pkg" / "module.py")
    _touch(tmp_path / "ns_pkg" / "sub" / "module.py")

    assert sorted(_find_namespace_packages(str(tmp_path))) == ["ns_pkg", "ns_pkg.sub"]


def test_find_namespace_packages_skips_node_modules_and_non_identifiers(tmp_path):
    _touch(tmp_path / "pkg" / "module.py")
    _touch(tmp_path / "node_modules" / "flatted" / "python" / "module.py")
    _touch(tmp_path / "ui-tests" / "conftest.py")

    assert _find_namespace_packages(str(tmp_path)) == ["pkg"]
