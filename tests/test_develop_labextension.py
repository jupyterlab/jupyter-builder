# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path
from unittest import mock

import pytest

from jupyter_builder import federated_extensions
from jupyter_builder.federated_extensions import develop_labextension, watch_labextension


def _make_extension(tmp_path):
    """Render the minimum an extension needs to be symlinked into a labextensions dir."""
    source = tmp_path / "myextension"
    (source / "static").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({"name": "myextension", "jupyterlab": {"outputDir": "static"}}),
    )
    return source


def test_develop_labextension_symlink_resolves_as_a_directory(tmp_path):
    """The installed symlink must be traversable as a directory.

    `Path.symlink_to` creates a *file* symlink on Windows unless
    `target_is_directory=True` is passed, even when the target is a directory,
    so the labextension directory cannot be traversed and the extension never
    loads. The flag is ignored on POSIX, which is why only the Windows CI legs
    can fail this assertion; the tests below fail on every platform.
    """
    source = _make_extension(tmp_path)

    full_dest = Path(
        develop_labextension(source, symlink=True, labextensions_dir=str(tmp_path / "labext")),
    )

    assert full_dest.is_symlink(), f"{full_dest} was not symlinked!"
    assert full_dest.is_dir(), (
        f"{full_dest} does not resolve as a directory; it was created as a file symlink."
    )
    assert (full_dest / "package.json").exists(), f"Cannot traverse into {full_dest}!"


def test_develop_labextension_marks_a_directory_symlink_as_a_directory(tmp_path):
    """`target_is_directory=True` must be passed when linking a directory.

    Asserted on the call rather than on the result because the flag has no
    observable effect on POSIX, so the behavioural test above would leave this
    regression invisible outside the two Windows CI legs.
    """
    source = _make_extension(tmp_path)

    with mock.patch.object(Path, "symlink_to", autospec=True) as symlink_to:
        develop_labextension(source, symlink=True, labextensions_dir=str(tmp_path / "labext"))

    assert symlink_to.call_count == 1
    assert symlink_to.call_args.kwargs.get("target_is_directory") is True, (
        f"symlink_to was called as {symlink_to.call_args}, which creates a file symlink on Windows."
    )


def test_develop_labextension_marks_a_file_symlink_as_a_file(tmp_path):
    """A single-file extension must not be linked as a directory.

    `develop_labextension` accepts a file as well as a directory, so the flag
    has to follow the target rather than being hardcoded to True.
    """
    source = tmp_path / "extension.js"
    source.write_text("")

    with mock.patch.object(Path, "symlink_to", autospec=True) as symlink_to:
        develop_labextension(source, symlink=True, labextensions_dir=str(tmp_path / "labext"))

    assert symlink_to.call_count == 1
    assert symlink_to.call_args.kwargs.get("target_is_directory") is False, (
        f"symlink_to was called as {symlink_to.call_args} for a file target."
    )


def test_watch_labextension_marks_the_output_symlink_as_a_directory(tmp_path):
    """`watch_labextension` links the output directory, so it must say so too.

    The link is created before any build happens, so the output directory need
    not exist yet and the flag cannot be inferred from the target.
    """
    source = _make_extension(tmp_path)
    labext = tmp_path / "labext"
    installed = labext / "myextension"
    # Not a symlink, so `watch_labextension` replaces it with one.
    installed.mkdir(parents=True)

    core_package_file = tmp_path / "core.package.json"
    core_package_file.write_text("{}")

    with (
        mock.patch.object(
            federated_extensions,
            "get_federated_extensions",
            return_value={"myextension": {"ext_dir": str(labext)}},
        ),
        mock.patch.object(Path, "symlink_to", autospec=True) as symlink_to,
        # Stop the run immediately after the code under test, so that none of
        # the node tooling needs to be available.
        mock.patch.object(
            federated_extensions,
            "_ensure_builder",
            side_effect=RuntimeError("stop after symlinking"),
        ),
        pytest.raises(RuntimeError, match="stop after symlinking"),
    ):
        watch_labextension(
            source,
            labextensions_path=[str(labext)],
            core_package_file=str(core_package_file),
        )

    assert symlink_to.call_count == 1
    assert symlink_to.call_args.kwargs.get("target_is_directory") is True, (
        f"symlink_to was called as {symlink_to.call_args}, which creates a file symlink on Windows."
    )
