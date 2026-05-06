"""Utilities for locating and resolving JupyterLab core package metadata."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import re
import subprocess
from pathlib import Path

import requests


def _home_dir() -> Path:
    home = os.environ.get("HOME")
    return Path(home) if home else Path.home()


def get_core_meta(
    version: str | None = None,
    ext_path: str | os.PathLike[str] | None = None,
) -> str:
    """Return the path to the core package JSON, downloading it if needed."""
    requested_version = version

    if requested_version is None:
        if ext_path is not None:
            installed_core_meta = _get_installed_core_meta(Path(ext_path).resolve())
            if installed_core_meta is not None:
                return installed_core_meta
        requested_version = "main"

    cache_root = _home_dir() / ".cache" / "jupyterlab_builder" / "core"
    cached_file = _get_cached_core_meta_file(cache_root, requested_version)
    if cached_file is not None:
        return str(cached_file)

    # Try to retrieve core meta from npm first
    try:
        npm_version = _resolve_npm_version(requested_version)
        npm_cache_file = cache_root / npm_version / "core.package.json"
        if npm_cache_file.exists():
            return str(npm_cache_file)
        _download_npm_core_meta(npm_version, npm_cache_file)
        return str(npm_cache_file)
    except requests.RequestException:
        pass  # Fallback to GitHub below

    github_cache_file = cache_root / requested_version / "core.package.json"
    _download_github_core_meta(requested_version, github_cache_file)
    return str(github_cache_file)


def _is_wildcard_version(version: str) -> bool:
    """Return True for npm range-style versions like 4.5.x."""
    return bool(re.search(r"\.x(\.|$)|(^|\.)x\.", version, flags=re.IGNORECASE))


def _resolve_npm_version(version: str) -> str:
    """Resolve an abstract version specifier to a concrete npm version string.

    - 'latest'  → fetches the current latest tag from npm
    - '4.5.x'   → fetches all published versions and returns the highest 4.5.x match
    - anything else is returned as-is (assumed to be a concrete version)
    """
    if version == "latest":
        r = requests.get("https://registry.npmjs.org/@jupyterlab/core-meta/latest", timeout=10)
        r.raise_for_status()
        latest_version = r.json().get("version")
        if not isinstance(latest_version, str) or not latest_version:
            msg = "Failed to resolve latest @jupyterlab/core-meta version from npm"
            raise requests.RequestException(msg)
        return latest_version

    if _is_wildcard_version(version):
        return _resolve_wildcard_npm_version(version)

    return version  # Concrete version like "4.2.5" — use directly


def _resolve_wildcard_npm_version(version: str) -> str:
    """Fetch the highest published npm version matching a wildcard range like '4.5.x'.

    Raises requests.RequestException if no matching version is found.
    """
    r = requests.get(
        "https://registry.npmjs.org/@jupyterlab/core-meta",
        headers={"Accept": "application/vnd.npm.install-v1+json"},
        timeout=10,
    )
    r.raise_for_status()
    all_versions: list[str] = list(r.json().get("versions", {}).keys())

    # Build a regex from the wildcard pattern, e.g. "4.5.x" → r"^4\.5\.\d+$"
    escaped = re.escape(version)
    wildcard_pattern = re.sub(r"x", r"\\d+", escaped, flags=re.IGNORECASE)
    pattern = "^" + wildcard_pattern + "$"

    matching = [v for v in all_versions if re.match(pattern, v)]
    if not matching:
        msg = f"No published @jupyterlab/core-meta versions match range '{version}'"
        raise requests.RequestException(msg)

    def semver_key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in re.split(r"[.\-]", v) if part.isdigit())

    return max(matching, key=semver_key)


def _get_cached_core_meta_file(cache_root: Path, version: str) -> Path | None:
    candidates = [
        cache_root / version / "core.package.json",
        cache_root / version / "package.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _download_npm_core_meta(version: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://unpkg.com/@jupyterlab/core-meta@{version}/core.package.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    destination.write_bytes(r.content)


def _download_github_core_meta(version: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = (
        "https://raw.githubusercontent.com/"
        f"jupyterlab/jupyterlab/{version}/"
        "jupyterlab/staging/package.json"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    destination.write_bytes(r.content)


def _get_installed_core_meta(ext_path: Path) -> str | None:
    if not (ext_path / "node_modules").exists():
        subprocess.check_call(["jlpm"], cwd=ext_path)  # noqa: S607

    target = ext_path
    while True:
        core_meta_path = target / "node_modules" / "@jupyterlab" / "core-meta"
        if (core_meta_path / "core.package.json").exists():
            return str(core_meta_path / "core.package.json")
        if target.parent == target:
            return None
        target = target.parent
