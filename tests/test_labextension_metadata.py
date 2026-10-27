# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from jupyter_builder.federated_extensions import _get_labextension_metadata


def test_get_labextension_metadata_accepts_installed_module_name(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "installed_labext").mkdir(parents=True)
    (site / "installed_labext" / "__init__.py").write_text(
        "def _jupyter_labextension_paths():\n"
        "    return [{'src': 'labextension', 'dest': 'installed-labext'}]\n",
    )
    monkeypatch.syspath_prepend(str(site))
    # The current directory has no `installed_labext` folder, so the module
    # name must be resolved by import rather than as a path.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    m, labexts = _get_labextension_metadata("installed_labext")

    assert m.__name__ == "installed_labext"
    assert labexts == [{"src": "labextension", "dest": "installed-labext"}]


def test_get_labextension_metadata_rejects_unknown_module_and_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="does not exist"):
        _get_labextension_metadata("no_such_labext_module")
