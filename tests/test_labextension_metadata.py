# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from jupyter_builder import federated_extensions
from jupyter_builder.federated_extensions import _get_labextension_metadata

_LABEXT_INIT = (
    "def _jupyter_labextension_paths():\n"
    "    return [{'src': 'labextension', 'dest': 'my-labext'}]\n"
)


def test_get_labextension_metadata_finds_package_in_path(tmp_path, monkeypatch):
    ext = tmp_path / "ext"
    (ext / "path_labext").mkdir(parents=True)
    (ext / "path_labext" / "__init__.py").write_text(_LABEXT_INIT)
    (ext / "pyproject.toml").write_text('[project]\nname = "path-labext"\n')
    monkeypatch.syspath_prepend(str(ext))
    # Pretend the package is installed so the lookup does not `pip install` it.
    monkeypatch.setattr(federated_extensions, "version", lambda _: "0.0.0")
    monkeypatch.chdir(tmp_path)

    m, labexts = _get_labextension_metadata(str(ext))

    assert m.__name__ == "path_labext"
    assert labexts == [{"src": "labextension", "dest": "my-labext"}]


def test_get_labextension_metadata_rejects_module_name(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "installed_labext").mkdir(parents=True)
    (site / "installed_labext" / "__init__.py").write_text(_LABEXT_INIT)
    monkeypatch.syspath_prepend(str(site))
    # Importable, but not a path relative to the current directory.
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="does not exist"):
        _get_labextension_metadata("installed_labext")
