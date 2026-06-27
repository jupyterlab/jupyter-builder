# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest

from jupyter_builder import core_path, federated_extensions
from jupyter_builder.federated_extensions import (
    _check_node_version,
    _ensure_builder,
    _read_rspack_node_range,
)


def _make_core_package_tarball(content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/core.package.json")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


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
        ext_path / "node_modules" / "@jupyterlab" / "core-meta" / "core.package.json",
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

    def fake_check_call(_args, cwd):
        (Path(cwd) / "node_modules").mkdir(parents=True)

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.6.0-alpha.4.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="4.6.0-alpha.4", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4",
        tarball_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json",
    )
    assert json.loads(
        (
            tmp_path
            / ".cache"
            / "jupyterlab_builder"
            / "core"
            / "4.6.0-alpha.4"
            / "core.package.json"
        ).read_text(),
    ) == {"devDependencies": {}}


def test_get_core_meta_falls_back_to_github_when_npm_fails(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/4.6.0-alpha.4/"
        "jupyterlab/staging/package.json"
    )
    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4":
            msg = "Not Found"
            raise urllib.error.URLError(msg)
        if url == github_url:
            return io.BytesIO(b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="4.6.0-alpha.4", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4",
        github_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json",
    )


def test_get_core_meta_wildcard_version_resolves_from_npm_and_downloads_core_meta(
    tmp_path,
    monkeypatch,
):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.3.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta":
            return io.BytesIO(
                json.dumps({"versions": {"4.5.0": {}, "4.5.3": {}, "4.6.0": {}}}).encode(),
            )
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.3":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="4.5.x", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta",
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.3",
        tarball_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.3" / "core.package.json",
    )


def test_resolve_wildcard_npm_version_returns_highest_match(monkeypatch):
    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        assert url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta"
        return io.BytesIO(
            json.dumps(
                {
                    "versions": {
                        "4.4.9": {},
                        "4.5.1": {},
                        "4.5.12": {},
                        "4.6.0-alpha.4": {},
                    },
                },
            ).encode(),
        )

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    resolved = core_path._resolve_wildcard_npm_version("4.5.x")

    assert resolved == "4.5.12"


def test_resolve_wildcard_npm_version_matches_prerelease_versions(monkeypatch):
    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        assert url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta"
        return io.BytesIO(
            json.dumps(
                {
                    "versions": {
                        "4.6.0-alpha.3": {},
                        "4.6.0-alpha.4": {},
                        "4.6.0-alpha.5": {},
                    },
                },
            ).encode(),
        )

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    resolved = core_path._resolve_wildcard_npm_version("4.6.x")

    assert resolved == "4.6.0-alpha.5"


def test_resolve_wildcard_npm_version_raises_when_no_matches(monkeypatch):
    monkeypatch.setattr(
        core_path.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(
            json.dumps({"versions": {"4.6.0": {}, "5.0.0": {}}}).encode(),
        ),
    )

    with pytest.raises(urllib.error.URLError, match="No published @jupyterlab/core-meta"):
        core_path._resolve_wildcard_npm_version("4.5.x")


def test_get_core_meta_latest_uses_npm_latest_and_caches_by_resolved_version(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.6.0-alpha.4.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            return io.BytesIO(json.dumps({"version": "4.6.0-alpha.4"}).encode())
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="latest", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest",
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.6.0-alpha.4",
        tarball_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.6.0-alpha.4" / "core.package.json",
    )


def test_ensure_builder_with_jupyter_builder(tmp_path):
    ext_path = tmp_path / "ext"
    core_path_dir = tmp_path / "core-meta"
    core_package_file = core_path_dir / "core.package.json"
    builder_dir = ext_path / "node_modules" / "@jupyter" / "builder"

    builder_dir.mkdir(parents=True)
    core_path_dir.mkdir()

    core_package_file.write_text(json.dumps({"devDependencies": {"@jupyter/builder": "^5.0.0"}}))
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyter/builder": "^5.0.0"}}),
    )
    (builder_dir / "package.json").write_text(json.dumps({"version": "5.0.0"}))

    builder_path, marker_pkg = _ensure_builder(str(ext_path), str(core_package_file))

    assert builder_path == str(builder_dir / "lib" / "build-labextension.js")
    assert marker_pkg == "@jupyter/builder"


def test_ensure_builder_with_jupyterlab_builder(tmp_path):
    ext_path = tmp_path / "ext"
    core_path_dir = tmp_path / "core-meta"
    core_package_file = core_path_dir / "core.package.json"
    builder_dir = ext_path / "node_modules" / "@jupyterlab" / "builder"

    builder_dir.mkdir(parents=True)
    core_path_dir.mkdir()

    core_package_file.write_text(json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}}))
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "^5.0.0"}}),
    )
    (builder_dir / "package.json").write_text(json.dumps({"version": "5.0.0"}))

    builder_path, marker_pkg = _ensure_builder(str(ext_path), str(core_package_file))

    assert builder_path == str(builder_dir / "lib" / "build-labextension.js")
    assert marker_pkg == "@jupyterlab/builder"


def _write_rspack(ext_path: Path, node_range: str) -> None:
    rspack_dir = ext_path / "node_modules" / "@rspack" / "core"
    rspack_dir.mkdir(parents=True)
    (rspack_dir / "package.json").write_text(json.dumps({"engines": {"node": node_range}}))


def test_read_rspack_node_range_reads_engines(tmp_path):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    _write_rspack(ext_path, "^20.19.0 || >=22.12.0")

    builder = str(ext_path / "node_modules" / "@jupyter" / "builder" / "lib" / "x.js")
    assert _read_rspack_node_range(builder, str(ext_path)) == "^20.19.0 || >=22.12.0"


def test_read_rspack_node_range_falls_back_when_missing(tmp_path):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()

    assert _read_rspack_node_range(str(ext_path), str(ext_path)) == ">=20.19.0"


def test_check_node_version_raises_on_old_node(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    _write_rspack(ext_path, "^20.19.0 || >=22.12.0")

    monkeypatch.setattr(federated_extensions, "_which_node_js", lambda: "node")
    monkeypatch.setattr(
        federated_extensions.subprocess,
        "check_output",
        lambda *_args, **_kwargs: b"v18.20.8\n",
    )

    with pytest.raises(RuntimeError, match=r"requires Node\.js .* \(found v18\.20\.8\)"):
        _check_node_version(str(ext_path), str(ext_path))


def test_check_node_version_passes_on_supported_node(tmp_path, monkeypatch):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    _write_rspack(ext_path, "^20.19.0 || >=22.12.0")

    monkeypatch.setattr(federated_extensions, "_which_node_js", lambda: "node")
    monkeypatch.setattr(
        federated_extensions.subprocess,
        "check_output",
        lambda *_args, **_kwargs: b"v22.12.0\n",
    )

    _check_node_version(str(ext_path), str(ext_path))
