# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json

import pytest

from jupyter_builder.federated_extensions import watch_labextension


def test_watch_labextension_symlinks_an_unbuilt_output_dir_as_a_directory(tmp_path):
    """An output directory linked before it is built must still be a directory link.

    Windows fixes the kind of a symlink when it is created and never morphs it
    to the target afterwards. It infers the kind from the target when one
    exists, which is why linking an already-built directory works without any
    flag. Here the link is made before the first build has produced the output
    directory, so unless `target_is_directory=True` is passed a file symlink is
    created and the build output stays unreachable through it.

    POSIX symlinks are untyped, so this can only fail on the Windows CI legs.
    """
    source = tmp_path / "myextension"
    source.mkdir()
    (source / "package.json").write_text(
        json.dumps(
            {
                "name": "myextension",
                "version": "0.1.0",
                "jupyterlab": {"outputDir": "static"},
            },
        ),
    )
    output_dir = source / "static"
    assert not output_dir.exists(), (
        "The output dir must be missing for this to be a regression test!"
    )

    # An installed copy that is not a symlink, so `watch_labextension` discovers
    # the extension and swaps the copy for a link to the output directory.
    labext = tmp_path / "labext"
    installed = labext / "myextension"
    installed.mkdir(parents=True)
    (installed / "package.json").write_text(
        json.dumps({"name": "myextension", "version": "0.1.0"}),
    )

    core_package_file = tmp_path / "core.package.json"
    core_package_file.write_text("{}")

    # The extension declares no builder, so the run stops on its own right after
    # the symlink is created and none of the node toolchain has to be present.
    with pytest.raises(ValueError, match="require a devDependency"):
        watch_labextension(
            source,
            labextensions_path=[str(labext)],
            core_package_file=str(core_package_file),
        )

    assert installed.is_symlink(), f"{installed} was not replaced by a symlink!"

    # Build, as the watch that follows the symlink would have done.
    output_dir.mkdir()
    (output_dir / "style.js").write_text("")

    assert installed.is_dir(), (
        f"{installed} does not resolve as a directory; it was created as a file "
        "symlink, so the build output cannot be reached through it."
    )
    assert (installed / "style.js").exists(), f"Cannot traverse into {installed}!"
