# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path

import pytest
import requests

from jupyter_builder import core_path
from jupyter_builder.federated_extensions import _ensure_builder


def test_get_core_meta_prefers_installed_core_meta(tmp_path):
    ext_path = tmp_path / "ext"
    core_meta_dir = ext_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    (core_meta_dir / "core.package.json").write_text("{}")

    location = core_path.get_core_meta(ext_path=str(ext_path))

    assert location == str(core_meta_dir / "core.package.json")


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
    assert location == str(
        ext_path / "node_modules" / "@jupyterlab" / "core-meta" / "core.package.json"
    )


def test_get_core_meta_uses_cache_for_explicit_version_before_installed(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    core_meta_dir = ext_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    (core_meta_dir / "core.package.json").write_text("{}")

    monkeypatch.setenv("HOME", str(tmp_path))
    cached_file = (
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "v-test" / "core.package.json"
    )
    cached_file.parent.mkdir(parents=True)
    cached_file.write_text('{"from": "cache"}')

    location = core_path.get_core_meta(version="v-test", ext_path=ext_path)

    assert location == str(cached_file)


def test_get_core_meta_fetches_npm_core_meta_before_github(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    def fake_check_call(args, cwd):
        (Path(cwd) / "node_modules").mkdir(parents=True)

    class FakeResponse:
        def __init__(self, content=b"", json_data=None):
            self.content = content
            self._json_data = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url == "https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json":
            return FakeResponse(content=b'{"devDependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(core_path.requests, "get", fake_get)

    location = core_path.get_core_meta(version="4.6.0-alpha.4", ext_path=ext_path)

    assert calls == ["https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json"]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json"
    )
    assert json.loads(
        (
            tmp_path
            / ".cache"
            / "jupyterlab_builder"
            / "core"
            / "4.6.0-alpha.4"
            / "core.package.json"
        ).read_text()
    ) == {"devDependencies": {}}


def test_get_core_meta_falls_back_to_github_when_npm_fails(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeResponse:
        def __init__(self, content=b"", json_data=None, should_fail=False):
            self.content = content
            self._json_data = json_data
            self._should_fail = should_fail

        def raise_for_status(self):
            if self._should_fail:
                msg = "failed"
                raise requests.HTTPError(msg)

        def json(self):
            return self._json_data

    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url == "https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json":
            return FakeResponse(should_fail=True)
        if url == (
            "https://raw.githubusercontent.com/"
            "jupyterlab/jupyterlab/4.6.0-alpha.4/"
            "jupyterlab/staging/package.json"
        ):
            return FakeResponse(content=b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.requests, "get", fake_get)

    location = core_path.get_core_meta(version="4.6.0-alpha.4", ext_path=ext_path)

    assert calls == [
        "https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json",
        "https://raw.githubusercontent.com/jupyterlab/jupyterlab/4.6.0-alpha.4/jupyterlab/staging/package.json",
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json"
    )


def test_get_core_meta_wildcard_version_resolves_from_npm_and_downloads_core_meta(
    tmp_path, monkeypatch
):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeResponse:
        def __init__(self, content=b"", json_data=None):
            self.content = content
            self._json_data = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == "https://registry.npmjs.org/@jupyterlab/core-meta":
            return FakeResponse(
                content=b"",
                json_data={"versions": {"4.5.0": {}, "4.5.3": {}, "4.6.0": {}}},
            )
        if url == "https://unpkg.com/@jupyterlab/core-meta@4.5.3/core.package.json":
            return FakeResponse(content=b'{"devDependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.requests, "get", fake_get)

    location = core_path.get_core_meta(version="4.5.x", ext_path=ext_path)

    assert calls == [
        "https://registry.npmjs.org/@jupyterlab/core-meta",
        "https://unpkg.com/@jupyterlab/core-meta@4.5.3/core.package.json",
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.3" / "core.package.json"
    )


def test_resolve_wildcard_npm_version_returns_highest_match(monkeypatch):
    class FakeResponse:
        def __init__(self, json_data):
            self._json_data = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    def fake_get(url, **kwargs):
        assert url == "https://registry.npmjs.org/@jupyterlab/core-meta"
        return FakeResponse(
            {
                "versions": {
                    "4.4.9": {},
                    "4.5.1": {},
                    "4.5.12": {},
                    "4.6.0-alpha.4": {},
                }
            }
        )

    monkeypatch.setattr(core_path.requests, "get", fake_get)

    resolved = core_path._resolve_wildcard_npm_version("4.5.x")

    assert resolved == "4.5.12"


def test_resolve_wildcard_npm_version_raises_when_no_matches(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"versions": {"4.6.0": {}, "5.0.0": {}}}

    monkeypatch.setattr(core_path.requests, "get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(requests.RequestException, match="No published @jupyterlab/core-meta"):
        core_path._resolve_wildcard_npm_version("4.5.x")


def test_get_core_meta_latest_uses_npm_latest_and_caches_by_resolved_version(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeResponse:
        def __init__(self, content=b"", json_data=None):
            self.content = content
            self._json_data = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_data

    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url == "https://registry.npmjs.org/@jupyterlab/core-meta/latest":
            return FakeResponse(json_data={"version": "4.6.0-alpha.4"})
        if url == "https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json":
            return FakeResponse(content=b'{"devDependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.requests, "get", fake_get)

    location = core_path.get_core_meta(version="latest", ext_path=ext_path)

    assert calls == [
        "https://registry.npmjs.org/@jupyterlab/core-meta/latest",
        "https://unpkg.com/@jupyterlab/core-meta@4.6.0-alpha.4/core.package.json",
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json"
    )


def test_ensure_builder_reads_custom_core_package_file(tmp_path):
    ext_path = tmp_path / "ext"
    core_path_dir = tmp_path / "core-meta"
    core_package_file = core_path_dir / "core.package.json"
    # Exercises the backwards-compatible @jupyterlab/builder path. The returned
    # builder script path matches the marker the extension declares.
    builder_dir = ext_path / "node_modules" / "@jupyterlab" / "builder"

    builder_dir.mkdir(parents=True)
    core_path_dir.mkdir()

    core_package_file.write_text(json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}}))
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}})
    )
    (builder_dir / "package.json").write_text(json.dumps({"version": "5.0.0"}))

    builder_path = _ensure_builder(str(ext_path), str(core_package_file))

    assert builder_path == str(builder_dir / "lib" / "build-labextension.js")
