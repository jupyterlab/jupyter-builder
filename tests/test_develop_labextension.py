# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path

import pytest

from jupyter_builder.federated_extensions import develop_labextension, watch_labextension

# `Path.symlink_to` creates a *file* symlink on Windows unless
# `target_is_directory=True` is passed, even when the target is a directory.
# A file symlink to a directory cannot be traversed, so the labextension is
# installed but unusable.
# The flag is ignored on POSIX, so these tests can only fail on the Windows CI legs.


def _make_extension(tmp_path):
    """Render the minimum an extension needs to be symlinked into a labextensions dir."""
    source = tmp_path / "myextension"
    (source / "static").mkdir(parents=True)
    (source / "static" / "style.js").write_text("")
    (source / "package.json").write_text(
        json.dumps(
            {
                "name": "myextension",
                "version": "0.1.0",
                "jupyterlab": {"outputDir": "static"},
            },
        ),
    )
    return source


def test_develop_labextension_symlinks_a_directory_as_a_directory(tmp_path):
    """The installed symlink must be traversable as a directory."""
    source = _make_extension(tmp_path)

    full_dest = Path(
        develop_labextension(source, symlink=True, labextensions_dir=str(tmp_path / "labext")),
    )

    assert full_dest.is_symlink(), f"{full_dest} was not symlinked!"
    assert full_dest.is_dir(), (
        f"{full_dest} does not resolve as a directory; it was created as a file symlink."
    )
    assert (full_dest / "package.json").exists(), f"Cannot traverse into {full_dest}!"


def test_develop_labextension_symlinks_a_file_as_a_file(tmp_path):
    """A single-file extension must be linked as a file, not as a directory.

    `develop_labextension` accepts a file as well as a directory, so the kind of
    link has to follow the target rather than being hardcoded to a directory.
    """
    source = tmp_path / "extension.js"
    source.write_text("console.log('extension');\n")

    full_dest = Path(
        develop_labextension(source, symlink=True, labextensions_dir=str(tmp_path / "labext")),
    )

    assert full_dest.is_symlink(), f"{full_dest} was not symlinked!"
    assert full_dest.is_file(), (
        f"{full_dest} does not resolve as a file; it was created as a directory symlink."
    )
    assert full_dest.read_text() == "console.log('extension');\n"


def test_watch_labextension_symlinks_the_output_dir_as_a_directory(tmp_path):
    """`watch_labextension` replaces an installed extension with a link to its output dir.

    The link is created before any build runs, so the output directory need not
    exist yet and the kind of link cannot be inferred from the target.
    """
    source = _make_extension(tmp_path)

    # An already-installed copy of the extension, so that `watch_labextension`
    # discovers it and swaps it for a symlink instead of installing it afresh.
    labext = tmp_path / "labext"
    installed = labext / "myextension"
    installed.mkdir(parents=True)
    (installed / "package.json").write_text(
        json.dumps({"name": "myextension", "version": "0.1.0"}),
    )

    core_package_file = tmp_path / "core.package.json"
    core_package_file.write_text("{}")

    # The extension declares no builder, so the run stops right after the
    # symlink is created and none of the node toolchain has to be present.
    with pytest.raises(ValueError, match="require a devDependency"):
        watch_labextension(
            source,
            labextensions_path=[str(labext)],
            core_package_file=str(core_package_file),
        )

    assert installed.is_symlink(), f"{installed} was not replaced by a symlink!"
    assert installed.is_dir(), (
        f"{installed} does not resolve as a directory; it was created as a file symlink."
    )
    assert (installed / "style.js").exists(), f"Cannot traverse into {installed}!"
