# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import sys

import pytest

from jupyter_builder.jlpm import _which_node_js


@pytest.mark.skipif(sys.platform == "win32", reason="requires POSIX symlinks")
def test_which_node_js_returns_symlink_path_unresolved(tmp_path):
    # Mimic a Volta-style setup where `node` is a symlink to a dispatcher
    # binary.
    dispatcher = tmp_path / "dispatcher"
    dispatcher.write_text("#!/bin/sh\n")
    dispatcher.chmod(0o755)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node_shim = bin_dir / "node"
    node_shim.symlink_to(dispatcher)

    assert _which_node_js(env={"PATH": str(bin_dir)}) == str(node_shim)
