# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Unit tests for the private core-path resolution helper.

Regression coverage for jupyterlab/jupyter-builder#180: an installed
`@jupyterlab/core-meta` package ships its own `package.json` (the npm
manifest, with no `jupyterlab` key) alongside `core.package.json` (the
actual core data). `_resolve_core_path_for_jupyterlab_builder` must hand
`@jupyterlab/builder` the core data, not the npm manifest, and must not
overwrite files it doesn't own inside `node_modules`.
"""

import json

from jupyter_builder.federated_extensions import (
    _resolve_core_path_for_jupyterlab_builder,
)

CORE_DATA = {"jupyterlab": {"singletonPackages": ["@jupyterlab/application"]}}
NPM_MANIFEST = {"name": "@jupyterlab/core-meta", "version": "4.6.2"}


def test_returns_the_directory_directly_when_already_named_package_json(tmp_path):
    core_file = tmp_path / "package.json"
    core_file.write_text(json.dumps(CORE_DATA))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    assert core_path == str(tmp_path)


def test_ignores_a_pre_existing_unrelated_package_json_next_to_the_core_file(tmp_path):
    """Reproduces #180: an installed @jupyterlab/core-meta ships both files."""
    core_meta_dir = tmp_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    core_file = core_meta_dir / "core.package.json"
    core_file.write_text(json.dumps(CORE_DATA))
    manifest_file = core_meta_dir / "package.json"
    manifest_file.write_text(json.dumps(NPM_MANIFEST))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    seen = json.loads((core_meta_dir.__class__(core_path) / "package.json").read_text())
    assert seen.get("jupyterlab") == CORE_DATA["jupyterlab"]

    # node_modules itself must be untouched: the installed manifest survives
    # exactly as npm published it.
    assert json.loads(manifest_file.read_text()) == NPM_MANIFEST


def test_does_not_write_into_node_modules_at_all(tmp_path):
    core_meta_dir = tmp_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    core_file = core_meta_dir / "core.package.json"
    core_file.write_text(json.dumps(CORE_DATA))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    assert "node_modules" not in core_path
    assert {p.name for p in core_meta_dir.iterdir()} == {"core.package.json"}
