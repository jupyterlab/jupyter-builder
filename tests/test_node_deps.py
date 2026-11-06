# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path

import pytest

from jupyter_builder import _node_deps
from jupyter_builder._node_deps import (
    ensure_dependencies_installed,
    find_in_node_modules,
    is_workspace_member,
    is_workspace_root,
)

PROBE = ("@jupyter", "builder")


def _install_probe(root: Path) -> None:
    (root / "node_modules" / "@jupyter" / "builder").mkdir(parents=True)


@pytest.fixture
def jlpm_calls(monkeypatch):
    """Record `jlpm` invocations instead of running them."""
    calls = []

    def fake_check_call(args, cwd):
        calls.append((args, Path(cwd)))

    monkeypatch.setattr(_node_deps.subprocess, "check_call", fake_check_call)
    return calls


@pytest.mark.parametrize(
    ("package_json", "pnpm_workspace", "expected"),
    [
        ({"workspaces": ["packages/*"]}, False, True),
        ({"workspaces": {"packages": ["packages/*"]}}, False, True),
        ({"workspaces": {"nohoist": ["**/foo"]}}, False, False),
        ({"workspaces": []}, False, False),
        ({"name": "standalone"}, False, False),
        (None, True, True),
        (None, False, False),
        ("{not json", False, False),
        (["not", "an", "object"], False, False),
    ],
)
def test_is_workspace_root(tmp_path, package_json, pnpm_workspace, expected):
    if isinstance(package_json, str):
        (tmp_path / "package.json").write_text(package_json)
    elif package_json is not None:
        (tmp_path / "package.json").write_text(json.dumps(package_json))
    if pnpm_workspace:
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")

    assert is_workspace_root(tmp_path) is expected


def _make_ext(path: Path, name: str) -> Path:
    path.mkdir(parents=True)
    (path / "package.json").write_text(json.dumps({"name": name}))
    return path


@pytest.mark.parametrize("name", ["ext", "@scope/ext"])
def test_is_workspace_member_when_linked(tmp_path, link_dir, name):
    ext_path = _make_ext(tmp_path / "packages" / "ext", name)
    link_dir(ext_path, tmp_path / "node_modules" / name)

    assert is_workspace_member(tmp_path, ext_path) is True


def test_is_workspace_member_without_link(tmp_path):
    ext_path = _make_ext(tmp_path / "tests" / "ext", "ext")
    (tmp_path / "node_modules").mkdir()

    assert is_workspace_member(tmp_path, ext_path) is False


def test_is_workspace_member_when_name_links_elsewhere(tmp_path, link_dir):
    member = _make_ext(tmp_path / "packages" / "ext", "ext")
    link_dir(member, tmp_path / "node_modules" / "ext")
    ext_path = _make_ext(tmp_path / "tests" / "ext", "ext")

    assert is_workspace_member(tmp_path, ext_path) is False


@pytest.mark.parametrize(
    "package_json",
    [None, "{not json", json.dumps(["not", "an", "object"]), json.dumps({"version": "1.0.0"})],
)
def test_is_workspace_member_without_usable_name(tmp_path, link_dir, package_json):
    ext_path = tmp_path / "packages" / "ext"
    ext_path.mkdir(parents=True)
    if package_json is not None:
        (ext_path / "package.json").write_text(package_json)
    # The link is valid, so only the missing/unusable name can reject it.
    link_dir(ext_path, tmp_path / "node_modules" / "ext")

    assert is_workspace_member(tmp_path, ext_path) is False


def test_find_in_node_modules_prefers_start(tmp_path):
    ext_path = tmp_path / "packages" / "ext"
    _install_probe(ext_path)
    _install_probe(tmp_path)

    assert find_in_node_modules(ext_path, PROBE) == ext_path


def test_find_in_node_modules_walks_up(tmp_path):
    ext_path = tmp_path / "packages" / "ext"
    ext_path.mkdir(parents=True)
    _install_probe(tmp_path)

    assert find_in_node_modules(ext_path, PROBE) == tmp_path


def test_find_in_node_modules_returns_none_at_filesystem_root(tmp_path):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()

    assert find_in_node_modules(ext_path, ("@jupyter", "does-not-exist-anywhere")) is None


def test_ensure_dependencies_installed_skips_with_local_node_modules(tmp_path, jlpm_calls):
    (tmp_path / "node_modules").mkdir()

    ensure_dependencies_installed(tmp_path, PROBE)

    assert jlpm_calls == []


def test_ensure_dependencies_installed_skips_for_workspace_member(
    tmp_path,
    jlpm_calls,
    link_dir,
):
    ext_path = _make_ext(tmp_path / "packages" / "ext", "ext")
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["packages/*"]}))
    _install_probe(tmp_path)
    link_dir(ext_path, tmp_path / "node_modules" / "ext")

    ensure_dependencies_installed(ext_path, PROBE)

    assert jlpm_calls == []


def test_ensure_dependencies_installed_installs_for_non_member_below_workspace_root(
    tmp_path,
    jlpm_calls,
):
    ext_path = _make_ext(tmp_path / "tests" / "mock_packages" / "ext", "ext")
    (ext_path / "yarn.lock").touch()
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["packages/*"]}))
    _install_probe(tmp_path)

    ensure_dependencies_installed(ext_path, PROBE)

    assert jlpm_calls == [(["jlpm"], ext_path)]


def test_ensure_dependencies_installed_installs_for_non_workspace_ancestor(tmp_path, jlpm_calls):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"name": "unrelated"}))
    _install_probe(tmp_path)

    ensure_dependencies_installed(ext_path, PROBE)

    assert jlpm_calls == [(["jlpm"], ext_path)]


def test_ensure_dependencies_installed_installs_when_unresolved(tmp_path, jlpm_calls):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()

    ensure_dependencies_installed(ext_path, ("@jupyter", "does-not-exist-anywhere"))

    assert jlpm_calls == [(["jlpm"], ext_path)]
