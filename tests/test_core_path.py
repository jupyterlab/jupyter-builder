# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import io
import json
import re
import sys
import tarfile
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from jupyter_builder import core_path, federated_extensions
from jupyter_builder.federated_extensions import (
    _check_node_version,
    _ensure_builder,
    _read_rspack_node_range,
    _resolve_core_path_for_jupyterlab_builder,
    _satisfies_allowing_prerelease,
)
from scripts import sync_core_meta


def _make_core_package_tarball(content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/core.package.json")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_jupyterlab_installed(monkeypatch):
    """Default to "jupyterlab is not installed" so tests are isolated from the dev environment.

    Tests that exercise the fallback-version compatibility check override this.
    """

    def _raise_not_found(_package):
        raise core_path.PackageNotFoundError(_package)

    monkeypatch.setattr(core_path, "installed_version", _raise_not_found)
    monkeypatch.setattr(core_path, "_installed_jupyterlab_core_meta", lambda: None)
    monkeypatch.delenv("JPBLD_OFFLINE", raising=False)


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

    # JupyterLab releases are published as git tags like "v4.5.7", so a numeric
    # version requested from GitHub must be looked up with the "v" prefix.
    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/v4.5.7/"
        "jupyterlab/staging/package.json"
    )
    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            msg = "Not Found"
            raise urllib.error.URLError(msg)
        if url == github_url:
            return io.BytesIO(b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="4.5.7", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7",
        github_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


def test_get_core_meta_accepts_v_prefixed_version(tmp_path, monkeypatch):
    """A 'v'-prefixed version is normalized so it resolves identically to the bare form."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/v4.5.7/"
        "jupyterlab/staging/package.json"
    )
    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            msg = "Not Found"
            raise urllib.error.URLError(msg)
        if url == github_url:
            return io.BytesIO(b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="v4.5.7", ext_path=ext_path)

    # Both the npm lookup and the cache directory use the normalized "4.5.7".
    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7",
        github_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


@pytest.mark.parametrize(
    ("version", "expected_ref"),
    [
        ("4.5.7", "v4.5.7"),
        ("4.6.0-alpha.4", "v4.6.0a4"),
        ("4.6.0-beta.1", "v4.6.0b1"),
        ("4.6.0-rc.2", "v4.6.0rc2"),
        ("main", "main"),
        ("some-branch", "some-branch"),
    ],
)
def test_github_ref_maps_versions_to_git_tags(version, expected_ref):
    assert core_path._github_ref(version) == expected_ref


@pytest.mark.parametrize("version", ["4.5.7", "v4.5.7"])
def test_normalize_version_accepts_both_forms(version):
    assert core_path._normalize_version(version) == "4.5.7"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # Partial specifiers are ranges over the omitted components.
        ("4", "4.x.x"),
        ("4.5", "4.5.x"),
        # Partially wildcarded ranges are completed the same way.
        ("4.x", "4.x.x"),
        ("4.X", "4.x.x"),
        ("4.*", "4.x.x"),
        ("4.5.*", "4.5.x"),
        ("4.5.X", "4.5.x"),
        # Nothing is constrained after a wildcard component.
        ("4.x.7", "4.x.x"),
        # A bare wildcard means "any version".
        ("*", "latest"),
        ("x", "latest"),
        # Concrete versions and non-numeric specifiers are left alone.
        ("4.5.7", "4.5.7"),
        ("4.5.x", "4.5.x"),
        ("4.6.0-alpha.4", "4.6.0-alpha.4"),
        ("latest", "latest"),
        ("main", "main"),
        ("some-branch", "some-branch"),
    ],
)
def test_expand_partial_version(version, expected):
    assert core_path._expand_partial_version(version) == expected


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        # A caret admits every later patch, so it becomes a patch wildcard; a tilde
        # and an explicit lower bound stay pinned to the patch they name.
        ("^4.5.7", "4.5.x"),
        ("~4.5.7", "4.5.7"),
        (">=v4.5.7", "4.5.7"),
        ("4.5.7", "4.5.7"),
        # A caret with no patch component is already a range of its own.
        ("^4.5", "4.5"),
        ("^4", "4"),
        ("^4.5.x", "4.5.x"),
        # A caret over a prerelease also allows every 4.6 patch.
        ("^4.6.0-alpha.4", "4.6.x"),
        # A union targets the newest JupyterLab the extension supports.
        ("^4.3.6 || ^3.6.8", "4.3.x"),
        ("^3 || ^4", "4"),
        ("^4.5 || ^4.4.2", "4.5"),
        # Alternatives are ranked by lower bound, so the tilde alternative wins here
        # even though the caret alternative resolves to a wildcard.
        ("^4.5.7 || ~4.6.0", "4.6.0"),
        # Prereleases lose to the stable release of the same version.
        ("~4.6.0-alpha.4 || ~4.6.0", "4.6.0"),
        # Numeric, not lexical, ordering across alternatives.
        ("~4.9.0 || ~4.10.0", "4.10.0"),
        ("4.5.x", "4.5.x"),
        # Specifiers that name no version at all.
        ("latest", None),
        ("main", None),
        ("*", None),
    ],
)
def test_range_lower_bound(spec, expected):
    assert core_path._range_lower_bound(spec) == expected


def test_get_core_meta_falls_back_to_github_for_prerelease(tmp_path, monkeypatch):
    """An npm-style prerelease that npm lacks is fetched from the matching git tag."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/v4.6.0a4/"
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


def test_get_core_meta_wildcard_resolves_from_github_when_npm_has_no_match(tmp_path, monkeypatch):
    """A wildcard that npm cannot satisfy is resolved against GitHub release tags."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    tags_page1 = f"{core_path._GITHUB_TAGS_API_URL}?per_page=100&page=1"
    tags_page2 = f"{core_path._GITHUB_TAGS_API_URL}?per_page=100&page=2"
    # 4.5.10 must win over 4.5.2 — confirms numeric (not lexical) ordering.
    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/v4.5.10/"
        "jupyterlab/staging/package.json"
    )
    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta":
            # npm publishes no 4.5.x, so the npm wildcard lookup finds no match.
            return io.BytesIO(json.dumps({"versions": {"4.6.0": {}}}).encode())
        if url == tags_page1:
            return io.BytesIO(
                json.dumps(
                    [
                        {"name": "v4.6.0"},
                        {"name": "v4.5.2"},
                        {"name": "v4.5.10"},
                        {"name": "v4.5.1"},
                    ],
                ).encode(),
            )
        if url == tags_page2:
            # Older tags with no 4.5.x match — resolution stops here.
            return io.BytesIO(json.dumps([{"name": "v4.4.9"}]).encode())
        if url == github_url:
            return io.BytesIO(b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(version="4.5.x", ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta",
        tags_page1,
        tags_page2,
        github_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.10" / "core.package.json",
    )


def test_get_core_meta_raises_when_requested_version_is_unresolvable(tmp_path, monkeypatch):
    """An explicitly requested version that exists nowhere must fail loudly."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    def fake_urlopen(*_args, **_kwargs):
        msg = "Not Found"
        raise urllib.error.URLError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Could not resolve @jupyterlab/core-meta"):
        core_path.get_core_meta(version="9.9.9", ext_path=ext_path)


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


def test_semver_key_orders_prerelease_series():
    """Pre-releases rank alpha < beta < rc < stable, by series before iteration."""
    versions = [
        "4.6.0",
        "4.6.0-rc.1",
        "4.6.0-alpha.4",
        "4.6.0-beta.1",
        "4.6.0-rc.0",
        "4.6.0-beta.2",
        "4.6.0-alpha.10",
        "4.6.0-alpha",
    ]

    assert sorted(versions, key=core_path._semver_key) == [
        # A pre-release that is a prefix of another ranks lower.
        "4.6.0-alpha",
        # Numeric identifiers compare as numbers, not lexically: alpha.4 < alpha.10.
        "4.6.0-alpha.4",
        "4.6.0-alpha.10",
        "4.6.0-beta.1",
        "4.6.0-beta.2",
        "4.6.0-rc.0",
        "4.6.0-rc.1",
        # The stable release outranks every pre-release of the same version.
        "4.6.0",
    ]


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("4.6.0-alpha.5", "4.6.0-beta.0"),
        ("4.6.0-beta.1", "4.6.0-rc.0"),
        ("4.6.0-alpha.9", "4.6.0-rc.0"),
        ("4.6.0-rc.2", "4.6.0"),
        ("4.6.0", "4.6.1-alpha.0"),
        # A numeric identifier ranks below an alphanumeric one.
        ("4.6.0-1", "4.6.0-alpha"),
    ],
)
def test_semver_key_ranks_prerelease_transitions(lower, higher):
    assert core_path._semver_key(lower) < core_path._semver_key(higher)


def test_resolve_wildcard_npm_version_advances_across_prerelease_series(monkeypatch):
    """A wildcard picks the newest series, not the highest number within an older one."""

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        assert url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta"
        return io.BytesIO(
            json.dumps(
                {
                    "versions": {
                        "4.7.0-alpha.9": {},
                        "4.7.0-beta.1": {},
                        "4.7.0-rc.0": {},
                    },
                },
            ).encode(),
        )

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    # No stable 4.7.0 yet, so the pre-release ordering is what decides the answer.
    assert core_path._resolve_wildcard_npm_version("4.7.x") == "4.7.0-rc.0"


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("~4.6.0-alpha.9 || ~4.6.0-beta.1", "4.6.0-beta.1"),
        ("~4.6.0-beta.1 || ~4.6.0-rc.0", "4.6.0-rc.0"),
        ("~4.6.0-rc.0 || ~4.6.0-alpha.9", "4.6.0-rc.0"),
    ],
)
def test_range_lower_bound_ranks_prerelease_alternatives(spec, expected):
    """Union alternatives are ranked with the same pre-release precedence."""
    assert core_path._range_lower_bound(spec) == expected


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


def test_get_core_meta_defaults_to_latest_when_not_installed(tmp_path, monkeypatch):
    """With no explicit version and no installed core-meta, the npm "latest" dist-tag is used."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.7.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            return io.BytesIO(json.dumps({"version": "4.5.7"}).encode())
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest",
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7",
        tarball_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


def test_get_core_meta_latest_falls_back_to_github_when_npm_unreachable(tmp_path, monkeypatch):
    """If npm is unreachable, "latest" is resolved to the newest GitHub release tag."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    github_url = (
        "https://raw.githubusercontent.com/"
        "jupyterlab/jupyterlab/v4.5.7/"
        "jupyterlab/staging/package.json"
    )
    latest_release = json.dumps({"tag_name": "v4.5.7"}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            msg = "Not Found"
            raise urllib.error.URLError(msg)
        if url == core_path._GITHUB_LATEST_RELEASE_API_URL:
            return io.BytesIO(latest_release)
        if url == github_url:
            return io.BytesIO(b'{"dependencies": {}}')
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest",
        core_path._GITHUB_LATEST_RELEASE_API_URL,
        github_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


def test_get_core_meta_fallback_raises_on_installed_jupyterlab_mismatch(tmp_path, monkeypatch):
    """A fallback-resolved version whose major.minor disagrees with jupyterlab is rejected."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.6.2")

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            return io.BytesIO(json.dumps({"version": "4.5.7"}).encode())
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=re.escape("building against 4.5.7 metadata")):
        core_path.get_core_meta(ext_path=ext_path)


def test_get_core_meta_fallback_allows_matching_installed_jupyterlab(tmp_path, monkeypatch):
    """A fallback-resolved version is accepted when its major.minor matches jupyterlab."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.5.0")

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.7.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            return io.BytesIO(json.dumps({"version": "4.5.7"}).encode())
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


def test_get_core_meta_explicit_version_skips_installed_jupyterlab_check(tmp_path, monkeypatch):
    """An explicitly requested version is trusted even if it disagrees with jupyterlab."""
    ext_path = tmp_path / "ext"
    core_meta_dir = tmp_path / "core-meta"
    core_meta_dir.mkdir()
    (core_meta_dir / "core.package.json").write_text('{"devDependencies": {}}')
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.6.2")

    cache_file = tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text('{"devDependencies": {}}')

    location = core_path.get_core_meta(version="4.5.7", ext_path=ext_path)

    assert location == str(cache_file)


def test_get_core_meta_resolves_to_legacy_builder_marker_version(tmp_path, monkeypatch):
    """With no installed core-meta, a legacy @jupyterlab/builder pin is used over "latest"."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    # A tilde allows only patches of 4.5.7, so it stays pinned to the version it names.
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "~4.5.7"}}),
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.7.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    calls = []

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        calls.append(url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)
    logger = mock.Mock()

    location = core_path.get_core_meta(ext_path=ext_path, logger=logger)

    # The "latest" dist-tag is never hit — the marker's own version is requested directly.
    assert calls == [
        f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7",
        tarball_url,
    ]
    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )
    logger.warning.assert_called_once()
    warning_message = logger.warning.call_args[0][0] % logger.warning.call_args[0][1:]
    assert "@jupyterlab/builder" in warning_message
    assert "core-meta 4.5.7" in warning_message


def test_get_core_meta_legacy_builder_marker_skips_installed_jupyterlab_check(
    tmp_path,
    monkeypatch,
):
    """A legacy-marker-resolved version is trusted like an explicit version, not a guess."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "~4.5.7"}}),
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.6.2")

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.7.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


def test_get_core_meta_ignores_legacy_builder_marker_workspace_spec(tmp_path, monkeypatch):
    """A path/workspace version spec isn't a real version, so it falls through to "latest"."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": "file:../builder"}}),
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    tarball_content = b'{"devDependencies": {}}'
    tarball_bytes = _make_core_package_tarball(tarball_content)
    tarball_url = f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/-/core-meta-4.5.7.tgz"
    registry_meta = json.dumps({"dist": {"tarball": tarball_url}}).encode()

    def fake_urlopen(req_or_url, **_kwargs):
        url = getattr(req_or_url, "full_url", req_or_url)
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/latest":
            return io.BytesIO(json.dumps({"version": "4.5.7"}).encode())
        if url == f"{core_path.JPBLD_NPM_URL}/@jupyterlab/core-meta/4.5.7":
            return io.BytesIO(registry_meta)
        if url == tarball_url:
            return io.BytesIO(tarball_bytes)
        msg = f"Unexpected URL {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", fake_urlopen)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert location == str(
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json",
    )


@pytest.mark.parametrize(
    ("version_spec", "expected"),
    [
        ("4.5.7", "4.5.7"),
        ("^4.5.7", "4.5.x"),
        ("~4.5.7", "4.5.7"),
        (">=4.5.7", "4.5.7"),
        # A union resolves to its highest alternative, whichever side it is on.
        ("^4.3.6 || ^3.6.8", "4.3.x"),
        ("^3.6.8 || ^4.3.6", "4.3.x"),
        ("^3.6.8 || ^4.3.6 || ^5.0.0", "5.0.x"),
        # Compound and hyphen ranges reduce to their lower bound.
        (">=4.3.6 <5.0.0", "4.3.6"),
        ("4.1.0 - 4.5.0", "4.1.0"),
        ("file:../builder", None),
        ("workspace:*", None),
        ("*", None),
    ],
)
def test_legacy_builder_marker_version_parses_spec(tmp_path, version_spec, expected):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@jupyterlab/builder": version_spec}}),
    )

    assert core_path._legacy_builder_marker_version(ext_path) == expected


def test_legacy_builder_marker_version_none_without_package_json(tmp_path):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()

    assert core_path._legacy_builder_marker_version(ext_path) is None


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

    assert _read_rspack_node_range(str(ext_path), str(ext_path)) == "^20.19.0 || >=22.12.0"


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


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # A prerelease of a version newer than the range is new enough to build.
        ("26.8.0-alpha.0.0.0", True),
        ("22.13.0-nightly1", True),
        ("20.19.1-alpha.1", True),
        # A prerelease of the oldest supported version predates it, so it is not.
        ("22.12.0-alpha.1", False),
        ("20.19.0-alpha.1", False),
        # Prereleases must not widen the range itself, including under an
        # upper bound: 21.0.0-alpha.1 is <21.0.0, but 21.0.0 is excluded.
        ("21.0.0-alpha.1", False),
        ("21.7.3-alpha.1", False),
        ("18.20.8-alpha.1", False),
        # Stable versions keep behaving as before.
        ("26.8.0", True),
        ("22.12.0", True),
        ("20.19.0", True),
        ("21.7.3", False),
        ("18.20.8", False),
        # Unparsable versions are rejected.
        ("not-a-version", False),
    ],
)
def test_satisfies_allowing_prerelease(version, expected):
    assert _satisfies_allowing_prerelease(version, "^20.19.0 || >=22.12.0") is expected


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


CORE_DATA = {"jupyterlab": {"singletonPackages": ["@jupyterlab/application"]}}
NPM_MANIFEST = {"name": "@jupyterlab/core-meta", "version": "4.6.2"}


def test_resolve_core_path_returns_directory_when_already_named_package_json(tmp_path):
    core_file = tmp_path / "package.json"
    core_file.write_text(json.dumps(CORE_DATA))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    assert core_path == str(tmp_path)


def test_resolve_core_path_ignores_pre_existing_unrelated_package_json(tmp_path):
    """Regression for #180: an installed @jupyterlab/core-meta ships both files."""
    core_meta_dir = tmp_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    core_file = core_meta_dir / "core.package.json"
    core_file.write_text(json.dumps(CORE_DATA))
    manifest_file = core_meta_dir / "package.json"
    manifest_file.write_text(json.dumps(NPM_MANIFEST))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    seen = json.loads((Path(core_path) / "package.json").read_text())
    assert seen.get("jupyterlab") == CORE_DATA["jupyterlab"]

    # node_modules itself must be untouched: the installed manifest survives
    # exactly as npm published it.
    assert json.loads(manifest_file.read_text()) == NPM_MANIFEST


def test_resolve_core_path_does_not_write_into_node_modules(tmp_path):
    core_meta_dir = tmp_path / "node_modules" / "@jupyterlab" / "core-meta"
    core_meta_dir.mkdir(parents=True)
    core_file = core_meta_dir / "core.package.json"
    core_file.write_text(json.dumps(CORE_DATA))

    core_path = _resolve_core_path_for_jupyterlab_builder(str(core_file))

    assert "node_modules" not in core_path
    assert {p.name for p in core_meta_dir.iterdir()} == {"core.package.json"}


# ------------------------------------------------------------------------------
# Bundled core-meta & offline fallback tests
# ------------------------------------------------------------------------------


def _bundled_version():
    return json.loads(core_path.BUNDLED_CORE_META_PATH.read_text())["version"]


def _forbid_network(monkeypatch):
    def forbidden_urlopen(*_args, **_kwargs):
        msg = "Network calls must not be made in offline mode"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", forbidden_urlopen)


def _fail_network(monkeypatch):
    def failing_urlopen(*_args, **_kwargs):
        msg = "Network unreachable"
        raise urllib.error.URLError(msg)

    monkeypatch.setattr(core_path.urllib.request, "urlopen", failing_urlopen)


def _make_ext(tmp_path, builder_spec=None):
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    (ext_path / "node_modules").mkdir()
    package = {"name": "ext"}
    if builder_spec is not None:
        package["devDependencies"] = {"@jupyterlab/builder": builder_spec}
    (ext_path / "package.json").write_text(json.dumps(package))
    return ext_path


def _install_fake_jupyterlab(tmp_path, monkeypatch, version):
    """Make an installed jupyterlab with its own staging/package.json discoverable."""
    staging = tmp_path / "site-packages" / "jupyterlab" / "staging"
    staging.mkdir(parents=True)
    (staging / "package.json").write_text(json.dumps({"version": version}))
    monkeypatch.setattr(
        core_path,
        "_installed_jupyterlab_core_meta",
        lambda: staging / "package.json",
    )
    return staging / "package.json"


def test_bundled_core_meta_exists_and_valid():
    """jupyter_builder ships a bundled core.package.json with a release version."""
    data = json.loads(core_path.BUNDLED_CORE_META_PATH.read_text())
    assert re.match(r"^\d+\.\d+\.\d+", data["version"])
    assert "jupyterlab" in data


def test_installed_jupyterlab_core_meta_finds_staging_without_import(tmp_path, monkeypatch):
    """The installed jupyterlab's staging/package.json is located without importing it."""
    monkeypatch.undo()
    package = tmp_path / "jupyterlab"
    (package / "staging").mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('must not be imported')")
    (package / "staging" / "package.json").write_text('{"version": "4.7.0"}')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "jupyterlab", raising=False)

    assert core_path._installed_jupyterlab_core_meta() == package / "staging" / "package.json"


def test_installed_jupyterlab_core_meta_none_without_staging(tmp_path, monkeypatch):
    monkeypatch.undo()
    (tmp_path / "jupyterlab").mkdir()
    (tmp_path / "jupyterlab" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "jupyterlab", raising=False)

    assert core_path._installed_jupyterlab_core_meta() is None


@pytest.mark.parametrize(
    ("core_meta_version", "constraint", "expected"),
    [
        # Any release stands in for "latest".
        ("4.6.4", "latest", True),
        # Ranges accept any version within them, not just the release a download
        # would resolve them to: nbdime's "^4.0.0" is satisfied by 4.6.4.
        ("4.6.4", "^4.0.0", True),
        ("4.6.4", "^4.5.0 || ^3.6.0", True),
        ("4.6.4", "4.x", True),
        ("4.6.4", "4.6", True),
        ("4.6.4", "~4.6.1", True),
        ("4.6.4", ">=4.3.0 <5", True),
        ("4.6.4", "4.6.4", True),
        # A prerelease of a version within the range counts.
        ("4.7.0-alpha.2", "^4.0.0", True),
        # Outside the range.
        ("4.6.4", "4.5.7", False),
        ("4.6.4", "~4.5.0", False),
        ("4.6.4", "^5.0.0", False),
        ("4.6.4", "3.x", False),
        # Mutable branch names are never satisfied by a release snapshot.
        ("4.6.4", "main", False),
        ("4.6.4", "feature-xyz", False),
        ("not-a-version", "latest", False),
    ],
)
def test_local_core_meta_satisfies(core_meta_version, constraint, expected):
    assert core_path._local_core_meta_satisfies(core_meta_version, constraint) is expected


def test_get_core_meta_offline_mode_uses_bundled(tmp_path, monkeypatch):
    """With JPBLD_OFFLINE and no jupyterlab installed, the bundled snapshot is used."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)

    location = core_path.get_core_meta(ext_path=ext_path)

    assert location == str(core_path.BUNDLED_CORE_META_PATH)


def test_get_core_meta_offline_mode_prefers_installed_jupyterlab(tmp_path, monkeypatch):
    """The installed jupyterlab's own metadata is preferred over the bundled snapshot."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.7.1")
    staging = _install_fake_jupyterlab(tmp_path, monkeypatch, "4.7.1")
    _forbid_network(monkeypatch)

    assert core_path.get_core_meta(ext_path=ext_path) == str(staging)


def test_get_core_meta_offline_mode_satisfies_legacy_builder_range(tmp_path, monkeypatch):
    """An extension still on @jupyterlab/builder ^4.0.0 (e.g. nbdime) builds offline."""
    ext_path = _make_ext(tmp_path, builder_spec="^4.0.0")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)

    assert core_path.get_core_meta(ext_path=ext_path) == str(core_path.BUNDLED_CORE_META_PATH)


def test_get_core_meta_offline_mode_skips_local_copy_outside_legacy_range(tmp_path, monkeypatch):
    """A local copy outside the extension's declared range is not used."""
    ext_path = _make_ext(tmp_path, builder_spec="~4.5.0")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)

    with pytest.raises(RuntimeError, match=re.escape("satisfies '~4.5.0'")):
        core_path.get_core_meta(ext_path=ext_path)


def test_get_core_meta_offline_mode_falls_through_to_bundled(tmp_path, monkeypatch):
    """When the installed jupyterlab is outside the range, the bundled snapshot is tried."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _install_fake_jupyterlab(tmp_path, monkeypatch, "3.6.8")
    _forbid_network(monkeypatch)

    location = core_path.get_core_meta(version=f"^{_bundled_version()}", ext_path=ext_path)

    assert location == str(core_path.BUNDLED_CORE_META_PATH)


def test_get_core_meta_offline_mode_does_not_invoke_jlpm_when_node_modules_missing(
    tmp_path,
    monkeypatch,
):
    """In offline mode, missing node_modules must not invoke jlpm."""
    ext_path = tmp_path / "ext"
    ext_path.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")

    def forbidden_check_call(*_args, **_kwargs):
        msg = "jlpm should not be invoked in offline mode"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.subprocess, "check_call", forbidden_check_call)

    assert core_path.get_core_meta(ext_path=ext_path) == str(core_path.BUNDLED_CORE_META_PATH)


def test_get_core_meta_offline_mode_prefers_cache(tmp_path, monkeypatch):
    """Previously downloaded metadata for the exact version is still reused offline."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)
    cache_file = tmp_path / ".cache" / "jupyterlab_builder" / "core" / "4.5.7" / "core.package.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text('{"version": "4.5.7"}')

    assert core_path.get_core_meta(version="4.5.7", ext_path=ext_path) == str(cache_file)


def test_local_core_meta_satisfies_exact_prerelease():
    """An exact prerelease constraint matches identical metadata."""
    assert core_path._local_core_meta_satisfies("4.7.0-alpha.2", "4.7.0-alpha.2")
    assert core_path._local_core_meta_satisfies("4.7.0-beta.1", "4.7.0-beta.1")
    assert not core_path._local_core_meta_satisfies("4.7.0-alpha.1", "4.7.0-alpha.2")


def test_get_core_meta_offline_mode_cached_semver_range(tmp_path, monkeypatch):
    """Cached concrete versions are found for semver ranges in offline mode."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)
    cache_dir = tmp_path / ".cache" / "jupyterlab_builder" / "core"
    file_457 = cache_dir / "4.5.7" / "core.package.json"
    file_457.parent.mkdir(parents=True)
    file_457.write_text('{"version": "4.5.7"}')
    file_458 = cache_dir / "4.5.8" / "core.package.json"
    file_458.parent.mkdir(parents=True)
    file_458.write_text('{"version": "4.5.8"}')

    assert core_path.get_core_meta(version="4.5.x", ext_path=ext_path) == str(file_458)


def test_get_core_meta_network_failure_falls_back_to_cached_semver_range(tmp_path, monkeypatch):
    """When network fails, cached versions satisfying semver ranges are used."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    _fail_network(monkeypatch)
    cache_dir = tmp_path / ".cache" / "jupyterlab_builder" / "core"
    file_457 = cache_dir / "4.5.7" / "core.package.json"
    file_457.parent.mkdir(parents=True)
    file_457.write_text('{"version": "4.5.7"}')

    assert core_path.get_core_meta(version="4.5.x", ext_path=ext_path) == str(file_457)


def _write_cache_entry(tmp_path, version, dirname=None):
    cache_file = (
        tmp_path / ".cache" / "jupyterlab_builder" / "core" / (dirname or version)
    ) / "core.package.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(json.dumps({"version": version}))
    return cache_file


def test_get_core_meta_offline_mode_cached_range_skips_out_of_range_and_branches(
    tmp_path,
    monkeypatch,
):
    """Releases outside the range and metadata cached under a branch name are skipped."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)
    expected = _write_cache_entry(tmp_path, "4.5.7")
    _write_cache_entry(tmp_path, "4.6.0")
    _write_cache_entry(tmp_path, "4.6.0-alpha.0")
    # e.g. left behind by `--core-version=main`; its contents change over time.
    _write_cache_entry(tmp_path, "4.5.9", dirname="main")

    assert core_path.get_core_meta(version="4.5.x", ext_path=ext_path) == str(expected)


def test_get_core_meta_offline_mode_ignores_cached_branch_metadata(tmp_path, monkeypatch):
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)
    expected = _write_cache_entry(tmp_path, "4.6.4")
    _write_cache_entry(tmp_path, "4.7.0-alpha.0", dirname="main")

    assert core_path.get_core_meta(ext_path=ext_path) == str(expected)


@pytest.mark.parametrize("version", [None, "^4.0.0", "4.x"])
def test_get_core_meta_offline_mode_prefers_installed_jupyterlab_over_cache(
    tmp_path,
    monkeypatch,
    version,
):
    """An older release cached by an earlier build doesn't shadow the installed jupyterlab."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.6.4")
    _forbid_network(monkeypatch)
    _write_cache_entry(tmp_path, "4.5.7")
    staging = _install_fake_jupyterlab(tmp_path, monkeypatch, "4.6.4")

    assert core_path.get_core_meta(version=version, ext_path=ext_path) == str(staging)


def test_get_core_meta_network_failure_prefers_installed_jupyterlab_over_cache(
    tmp_path,
    monkeypatch,
):
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "4.6.4")
    _fail_network(monkeypatch)
    _write_cache_entry(tmp_path, "4.5.7")
    staging = _install_fake_jupyterlab(tmp_path, monkeypatch, "4.6.4")

    assert core_path.get_core_meta(ext_path=ext_path) == str(staging)


def test_get_core_meta_offline_mode_prefers_cache_over_bundled(tmp_path, monkeypatch):
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)
    expected = _write_cache_entry(tmp_path, "4.6.3")

    assert core_path.get_core_meta(version="~4.6.0", ext_path=ext_path) == str(expected)


def test_get_core_meta_offline_finds_ancestor_node_modules(tmp_path, monkeypatch):
    """Offline mode skips jlpm but continues searching ancestor node_modules."""
    workspace_root = tmp_path / "workspace"
    hoisted_meta = (
        workspace_root / "node_modules" / "@jupyterlab" / "core-meta" / "core.package.json"
    )
    hoisted_meta.parent.mkdir(parents=True)
    hoisted_meta.write_text('{"version": "4.6.4"}')

    ext_path = workspace_root / "packages" / "my-ext"
    ext_path.mkdir(parents=True)
    (ext_path / "package.json").write_text('{"name": "my-ext"}')

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")

    def forbidden_check_call(*_args, **_kwargs):
        msg = "jlpm should not be invoked in offline mode"
        raise AssertionError(msg)

    monkeypatch.setattr(core_path.subprocess, "check_call", forbidden_check_call)

    assert core_path.get_core_meta(ext_path=ext_path) == str(hoisted_meta)


@pytest.mark.parametrize("version", ["9.9.9", "4.5.7", "main"])
def test_get_core_meta_offline_mode_raises_on_incompatible_version(tmp_path, monkeypatch, version):
    """JPBLD_OFFLINE fails loudly when no local copy satisfies the requested version."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    _forbid_network(monkeypatch)

    with pytest.raises(RuntimeError, match="JPBLD_OFFLINE is set, but no local copy"):
        core_path.get_core_meta(version=version, ext_path=ext_path)


def test_get_core_meta_offline_mode_raises_on_installed_jupyterlab_mismatch(
    tmp_path,
    monkeypatch,
):
    """Without a version to go by, the bundled snapshot must match installed jupyterlab."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JPBLD_OFFLINE", "1")
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "9.0.0")
    _forbid_network(monkeypatch)

    expected_msg = r"building against .* metadata but jupyterlab 9\.0\.0 is installed"
    with pytest.raises(RuntimeError, match=expected_msg):
        core_path.get_core_meta(ext_path=ext_path)


def test_get_core_meta_network_failure_falls_back_to_bundled(tmp_path, monkeypatch, caplog):
    """When npm and GitHub are unreachable, the bundled snapshot is used with a warning."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    _fail_network(monkeypatch)
    logger = core_path.logging.getLogger("test-core-path")

    location = core_path.get_core_meta(ext_path=ext_path, logger=logger)

    assert location == str(core_path.BUNDLED_CORE_META_PATH)
    assert "Could not download @jupyterlab/core-meta" in caplog.text
    # The snapshot is used in place, not copied into the download cache.
    assert not (tmp_path / ".cache").exists()


def test_get_core_meta_network_failure_falls_back_to_installed_jupyterlab(tmp_path, monkeypatch):
    ext_path = _make_ext(tmp_path, builder_spec="^4.0.0")
    monkeypatch.setenv("HOME", str(tmp_path))
    staging = _install_fake_jupyterlab(tmp_path, monkeypatch, "4.2.0")
    _fail_network(monkeypatch)

    assert core_path.get_core_meta(ext_path=ext_path) == str(staging)


def test_get_core_meta_network_failure_raises_without_compatible_local_copy(
    tmp_path,
    monkeypatch,
):
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    _fail_network(monkeypatch)

    with pytest.raises(
        RuntimeError,
        match=r"Could not resolve .* no local copy .* satisfies '9\.9\.9'",
    ):
        core_path.get_core_meta(version="9.9.9", ext_path=ext_path)


def test_get_core_meta_network_failure_fallback_raises_on_jupyterlab_mismatch(
    tmp_path,
    monkeypatch,
):
    """Network fallback is rejected if the bundled version mismatches installed jupyterlab."""
    ext_path = _make_ext(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_path, "installed_version", lambda _package: "9.0.0")
    _fail_network(monkeypatch)

    expected_msg = r"building against .* metadata but jupyterlab 9\.0\.0 is installed"
    with pytest.raises(RuntimeError, match=expected_msg):
        core_path.get_core_meta(ext_path=ext_path)


def test_sync_core_meta_check_passes_when_synced(tmp_path, monkeypatch):
    """Verify that sync_core_meta(check=True) succeeds when source and target match."""
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    content = '{"name": "@jupyterlab/core-meta", "version": "4.6.3"}'
    source.write_text(content)
    target.write_text(content)

    monkeypatch.setattr(sync_core_meta, "SOURCE", source)
    monkeypatch.setattr(sync_core_meta, "TARGET", target)

    assert sync_core_meta.sync_core_meta(check=True) == 0


def test_sync_core_meta_detects_out_of_sync(tmp_path, monkeypatch):
    """Verify that sync_core_meta(check=True) returns 1 when files differ and syncs on update."""
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"

    source.write_text('{"version": "4.6.4"}')
    target.write_text('{"version": "4.6.3"}')

    monkeypatch.setattr(sync_core_meta, "SOURCE", source)
    monkeypatch.setattr(sync_core_meta, "TARGET", target)

    assert sync_core_meta.sync_core_meta(check=True) == 1
    assert sync_core_meta.sync_core_meta(check=False) == 0
    assert target.read_text() == '{"version": "4.6.4"}'
    assert sync_core_meta.sync_core_meta(check=True) == 0


@pytest.mark.skipif(
    not sync_core_meta.SOURCE.exists(),
    reason="requires node_modules/@jupyterlab/core-meta (run jlpm install)",
)
def test_sync_core_meta_checkout_is_in_sync():
    """Verify that the repository copy of core.package.json is in sync with node_modules."""
    assert sync_core_meta.sync_core_meta(check=True) == 0
