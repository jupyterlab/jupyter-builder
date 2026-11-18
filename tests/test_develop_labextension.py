# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import shutil
from pathlib import Path

import pytest

from jupyter_builder.federated_extensions import develop_labextension


def test_develop_labextension_creates_symlink(tmp_path):
    ext_dir = tmp_path / "my_ext"
    ext_dir.mkdir()
    (ext_dir / "package.json").write_text("{}")

    labext_dir = tmp_path / "labextensions"
    labext_dir.mkdir()

    dest = develop_labextension(
        str(ext_dir),
        labextensions_dir=str(labext_dir),
        destination="my_ext",
        symlink=True,
    )
    dest_path = Path(dest)
    assert dest_path.is_symlink()
    assert dest_path.resolve() == ext_dir.resolve()


def test_develop_labextension_replaces_broken_symlink(tmp_path):
    ext_dir = tmp_path / "my_ext"
    ext_dir.mkdir()
    (ext_dir / "package.json").write_text("{}")

    labext_dir = tmp_path / "labextensions"
    labext_dir.mkdir()

    # Initial symlink
    dest = develop_labextension(
        str(ext_dir),
        labextensions_dir=str(labext_dir),
        destination="my_ext",
        symlink=True,
    )
    dest_path = Path(dest)
    assert dest_path.is_symlink()

    # Delete source directory to turn dest into a broken/dangling symlink
    shutil.rmtree(ext_dir)
    assert not dest_path.exists()
    assert dest_path.is_symlink()

    # Re-run develop with new or recreated source - should replace dangling symlink
    new_ext_dir = tmp_path / "recreated_ext"
    new_ext_dir.mkdir()
    (new_ext_dir / "package.json").write_text("{}")

    new_dest = develop_labextension(
        str(new_ext_dir),
        labextensions_dir=str(labext_dir),
        destination="my_ext",
        symlink=True,
    )
    new_dest_path = Path(new_dest)
    assert new_dest_path.is_symlink()
    assert new_dest_path.exists()
    assert new_dest_path.resolve() == new_ext_dir.resolve()


def test_develop_labextension_raises_when_destination_is_not_symlink(tmp_path):
    ext_dir = tmp_path / "my_ext"
    ext_dir.mkdir()
    (ext_dir / "package.json").write_text("{}")

    labext_dir = tmp_path / "labextensions"
    labext_dir.mkdir()

    # Create real directory at destination
    real_dir = labext_dir / "my_ext"
    real_dir.mkdir()

    with pytest.raises(ValueError, match="exists and is not a symlink"):
        develop_labextension(
            str(ext_dir),
            labextensions_dir=str(labext_dir),
            destination="my_ext",
            symlink=True,
        )
