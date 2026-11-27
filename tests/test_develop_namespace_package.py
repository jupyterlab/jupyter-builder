# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import types
from pathlib import Path
from unittest import mock

from jupyter_builder.federated_extensions import develop_labextension_py


def test_develop_labextension_py_namespace_package(tmp_path):
    """develop_labextension_py should resolve base_path from __path__ for namespace packages."""
    ns_pkg = types.ModuleType("my_ns_pkg")
    ns_pkg.__file__ = None
    pkg_dir = tmp_path / "my_ns_pkg"
    pkg_dir.mkdir()
    ns_pkg.__path__ = [str(pkg_dir)]

    static_dir = pkg_dir / "static"
    static_dir.mkdir()
    (static_dir / "remoteEntry.js").write_text("// remoteEntry")

    labexts = [{"src": "static", "dest": "my-ns-ext"}]
    labext_dir = tmp_path / "labextensions"
    labext_dir.mkdir()

    with mock.patch(
        "jupyter_builder.federated_extensions._get_labextension_metadata",
        return_value=(ns_pkg, labexts),
    ):
        dests = develop_labextension_py(
            "my_ns_pkg",
            labextensions_dir=str(labext_dir),
            symlink=True,
        )

    assert len(dests) == 1
    dest_path = Path(dests[0])
    assert dest_path.is_symlink()
    assert (dest_path / "remoteEntry.js").exists()


def test_develop_labextension_py_fallback_cwd_when_no_file_or_path(tmp_path):
    """Fallback gracefully to current working directory when module lacks file and path."""
    mod = types.ModuleType("virtual_mod")
    mod.__file__ = None
    mod.__path__ = []

    labexts: list[dict[str, str]] = []
    labext_dir = tmp_path / "labextensions"
    labext_dir.mkdir()

    with mock.patch(
        "jupyter_builder.federated_extensions._get_labextension_metadata",
        return_value=(mod, labexts),
    ):
        dests = develop_labextension_py(
            "virtual_mod",
            labextensions_dir=str(labext_dir),
        )

    assert dests == []
