# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path

from jupyter_builder import core_path
from jupyter_builder.federated_extensions import _ensure_builder


def test_get_core_meta_prefers_installed_core_meta(tmp_path):
    ext_path = tmp_path / "ext"
    core_meta_dir = ext_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    (core_meta_dir / "core.package.json").write_text("{}")

    location = core_path.get_core_meta(ext_path=str(ext_path))

    assert location.path == str(core_meta_dir)
    assert location.package_file == "core.package.json"


def test_get_core_meta_installs_dependencies_before_searching(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    calls = []

    def fake_check_call(args, cwd):
        calls.append((args, Path(cwd)))
        core_meta_dir = Path(cwd) / "node_modules" / "@jupyterlab" / "core-meta"
        core_meta_dir.mkdir(parents=True)
        (core_meta_dir / "core.package.json").write_text("{}")

    monkeypatch.setattr(core_path.subprocess, "check_call", fake_check_call)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert calls == [(["jlpm"], ext_path)]
    assert location.path == str(ext_path / "node_modules" / "@jupyterlab" / "core-meta")
    assert location.package_file == "core.package.json"


def test_get_core_meta_falls_back_to_cached_package_json(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    def fake_check_call(args, cwd):
        (Path(cwd) / "node_modules").mkdir(parents=True)

    class FakeResponse:
        content = b'{"dependencies": {}}'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(core_path.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(core_path.requests, "get", lambda *args, **kwargs: FakeResponse())

    location = core_path.get_core_meta(version="v-test", ext_path=ext_path)

    assert location.path == str(tmp_path / ".cache" / "jupyterlab_builder" / "core" / "v-test")
    assert location.package_file == "package.json"
    assert json.loads(
        (
            tmp_path / ".cache" / "jupyterlab_builder" / "core" / "v-test" / "package.json"
        ).read_text()
    ) == {"dependencies": {}}


def test_ensure_builder_reads_custom_core_package_file(tmp_path):
    ext_path = tmp_path / "ext"
    core_path_dir = tmp_path / "core-meta"
    builder_dir = ext_path / "node_modules" / "@jupyterlab" / "builder"

    builder_dir.mkdir(parents=True)
    core_path_dir.mkdir()

    (core_path_dir / "core.package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}})
    )
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}})
    )
    (builder_dir / "package.json").write_text(json.dumps({"version": "5.0.0"}))

    builder_path = _ensure_builder(
        str(ext_path),
        str(core_path_dir),
        core_package_file="core.package.json",
    )

    assert builder_path == str(builder_dir / "lib" / "build-labextension.js")
