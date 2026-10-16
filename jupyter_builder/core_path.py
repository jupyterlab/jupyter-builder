"""Utilities for locating and resolving JupyterLab core package metadata."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import importlib.util
import io
import json
import logging
import os
import re
import subprocess
import tarfile
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

from .constants import JPBLD_NPM_URL, JPBLD_RAW_GITHUB_URL
from .jupyterlab_semver import make_range, make_semver

#: Snapshot of `@jupyterlab/core-meta` shipped with jupyter-builder, used as a last
#: resort when the metadata cannot be downloaded. It is kept byte-for-byte in sync with
#: the `@jupyterlab/core-meta` pinned in yarn.lock by `scripts/sync_core_meta.py`.
BUNDLED_CORE_META_PATH = Path(__file__).resolve().parent / "core.package.json"

_MAX_CORE_META_BYTES = 5 * 1024 * 1024  # 5 MB — generous upper bound for core.package.json

#: GitHub API endpoint used to resolve wildcard versions to concrete release tags
_GITHUB_TAGS_API_URL = "https://api.github.com/repos/jupyterlab/jupyterlab/tags"

#: GitHub API endpoint used to resolve "latest" to the newest stable release
_GITHUB_LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/jupyterlab/jupyterlab/releases/latest"
)

#: Upper bound on tag-list pages fetched when resolving a wildcard (100 tags per page)
_MAX_GITHUB_TAG_PAGES = 10

#: Pre-migration marker package.
_LEGACY_BUILDER_MARKER = "@jupyterlab/builder"

#: A version specifier built only from numeric and wildcard components, e.g. "4",
#: "4.5", "4.x" or "4.5.*". These are npm ranges rather than concrete versions.
_NUMERIC_OR_WILDCARD_SPEC = re.compile(r"[\dxX*]+(?:\.[\dxX*]+)*")


def _home_dir() -> Path:
    home = os.environ.get("HOME")
    return Path(home) if home else Path.home()


def _is_offline() -> bool:
    """Return True if offline mode is explicitly requested via JPBLD_OFFLINE."""
    return os.getenv("JPBLD_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def _installed_jupyterlab_core_meta() -> Path | None:
    """Return the core metadata shipped by the installed `jupyterlab` Python package.

    JupyterLab ships `jupyterlab/staging/package.json`, from which every
    `@jupyterlab/core-meta` release is copied, so it is the exact metadata of the
    JupyterLab installed alongside. The package is located without being imported.
    """
    try:
        spec = importlib.util.find_spec("jupyterlab")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        candidate = Path(location) / "staging" / "package.json"
        if candidate.is_file():
            return candidate
    return None


def _read_core_meta_version(core_meta: Path) -> str | None:
    try:
        with core_meta.open() as fid:
            version = json.load(fid).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and version else None


def _satisfies_allowing_prerelease(current: str, version_range: str) -> bool:
    """Return whether ``current`` satisfies ``version_range``, counting prereleases.

    A prerelease has to clear the comparators both as itself and as its release,
    so it can neither reach under a lower bound nor slip beneath an upper one:
    ``22.12.0-alpha.1`` sorts before the ``22.12.0`` it needs to be, and
    ``21.0.0-alpha.1`` is only ``<21.0.0`` because 21 is excluded to begin with.
    """
    try:
        range_ = make_range(version_range, loose=True)  # type: ignore[no-untyped-call]
        version = make_semver(current, loose=True)  # type: ignore[no-untyped-call]
    except Exception:  # noqa: BLE001
        return False
    candidates = [version]
    if version.prerelease:
        release = f"{version.major}.{version.minor}.{version.patch}"
        candidates.append(make_semver(release, loose=True))  # type: ignore[no-untyped-call]
    return any(
        all(comparator.test(candidate) for candidate in candidates for comparator in comparator_set)
        for comparator_set in range_.set
    )


def _local_core_meta_satisfies(core_meta_version: str, constraint: str) -> bool:
    """Return whether locally available metadata can stand in for `constraint`.

    `constraint` is the npm range the build asked for, e.g. "^4.0.0" from a legacy
    `@jupyterlab/builder` pin or "4.5.7" from `--core-version`. Unlike a download,
    which resolves the range to one release, any version within it will do here.
    "latest" accepts any release; branch names such as "main" are mutable and are
    never satisfied by a release snapshot.
    """
    if constraint == "latest":
        return bool(re.match(r"\d", core_meta_version))
    try:
        if make_range(constraint, loose=True).test(core_meta_version):  # type: ignore[no-untyped-call]
            return True
    except Exception:  # noqa: BLE001
        return False
    return _satisfies_allowing_prerelease(core_meta_version, constraint)


def _resolve_cached_core_meta(
    cache_root: Path,
    constraint: str,
    used_fallback_resolution: bool,
    logger: logging.Logger | None,
) -> tuple[Path, str] | None:
    """Find a concrete version cached in `cache_root` that satisfies `constraint`.

    Returns `(path, version)` for the highest matching version, or None if no cached
    version satisfies the constraint.
    """
    if not cache_root.is_dir():
        return None
    matches: list[tuple[Path, str]] = []
    try:
        entries = list(cache_root.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.is_dir():
            continue
        core_meta = _get_cached_core_meta_file(cache_root, entry.name)
        if core_meta is None or not core_meta.is_file():
            continue
        version = _read_core_meta_version(core_meta) or entry.name
        if not re.match(r"^\d+\.\d+\.\d+", version):
            continue
        if _local_core_meta_satisfies(version, constraint):
            matches.append((core_meta, version))
    if not matches:
        return None
    matches.sort(key=lambda item: _semver_key(item[1]), reverse=True)
    for core_meta, version in matches:
        _check_matches_installed_jupyterlab(version, used_fallback_resolution, logger)
        return core_meta, version
    return None


def _resolve_local_core_meta(
    constraint: str,
    used_fallback_resolution: bool,
    logger: logging.Logger | None,
    cache_root: Path | None = None,
) -> tuple[Path, str] | None:
    """Find core metadata available without network access that satisfies `constraint`.

    The local cache is checked first for concrete versions satisfying `constraint`.
    Next, the installed JupyterLab's own metadata is preferred: it is what the extension
    will run against in this environment, and it never goes stale. The snapshot bundled
    with jupyter-builder is the last resort, for environments without JupyterLab installed.

    Returns `(path, version)`, or None if neither is available and compatible.
    """
    if cache_root is None:
        cache_root = _home_dir() / ".cache" / "jupyterlab_builder" / "core"

    cached = _resolve_cached_core_meta(cache_root, constraint, used_fallback_resolution, logger)
    if cached is not None:
        return cached

    for core_meta in (_installed_jupyterlab_core_meta(), BUNDLED_CORE_META_PATH):
        if core_meta is None or not core_meta.is_file():
            continue
        core_meta_version = _read_core_meta_version(core_meta)
        if core_meta_version is None or not _local_core_meta_satisfies(
            core_meta_version,
            constraint,
        ):
            continue
        _check_matches_installed_jupyterlab(core_meta_version, used_fallback_resolution, logger)
        return core_meta, core_meta_version
    return None


def _no_local_core_meta_message(constraint: str) -> str:
    installed = _installed_jupyterlab_core_meta()
    installed_version = _read_core_meta_version(installed) if installed else None
    bundled_version = _read_core_meta_version(BUNDLED_CORE_META_PATH)
    return (
        f"no local copy of @jupyterlab/core-meta satisfies {constraint!r} "
        f"(installed jupyterlab: {installed_version or 'not found'}, "
        f"bundled with jupyter-builder: {bundled_version or 'not found'}). "
        "Pass --core-package-file to build against a specific core.package.json."
    )


def _http_get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 10) -> bytes:
    if not url.startswith(("http:", "https:")):
        msg = "URL must start with 'http:' or 'https:'"
        raise ValueError(msg)
    request_headers = {"User-Agent": "jupyter-builder"}
    if headers:
        request_headers.update(headers)
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        request_headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=request_headers)  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return bytes(resp.read())


def _offline_core_meta(
    constraint: str,
    used_fallback_resolution: bool,
    logger: logging.Logger | None,
    cache_root: Path | None = None,
) -> str:
    local = _resolve_local_core_meta(
        constraint,
        used_fallback_resolution,
        logger,
        cache_root=cache_root,
    )
    if local is None:
        msg = f"JPBLD_OFFLINE is set, but {_no_local_core_meta_message(constraint)}"
        raise RuntimeError(msg)
    core_meta, core_meta_version = local
    if logger:
        logger.info(
            "JPBLD_OFFLINE is set; using @jupyterlab/core-meta %s from %s.",
            core_meta_version,
            core_meta,
        )
    return str(core_meta)


def _download_core_meta(
    cache_root: Path,
    requested_version: str,
    constraint: str,
    used_fallback_resolution: bool,
    logger: logging.Logger | None,
) -> str:
    """Download core.package.json from npm or GitHub, falling back to a local copy."""
    try:
        npm_version = _resolve_npm_version(requested_version)
        _check_matches_installed_jupyterlab(npm_version, used_fallback_resolution, logger)
        npm_cache_file = cache_root / npm_version / "core.package.json"
        if npm_cache_file.exists():
            return str(npm_cache_file)
        _download_npm_core_meta(npm_version, npm_cache_file)
        return str(npm_cache_file)
    except urllib.error.URLError as npm_error:
        try:
            github_version = _resolve_github_version(requested_version)
            _check_matches_installed_jupyterlab(
                github_version,
                used_fallback_resolution,
                logger,
            )
            github_cache_file = cache_root / github_version / "core.package.json"
            if github_cache_file.exists():
                return str(github_cache_file)
            _download_github_core_meta(_github_ref(github_version), github_cache_file)
            return str(github_cache_file)
        except urllib.error.URLError as github_error:
            local = _resolve_local_core_meta(
                constraint,
                used_fallback_resolution,
                logger,
                cache_root=cache_root,
            )
            if local is not None:
                core_meta, core_meta_version = local
                if logger:
                    logger.warning(
                        "\033[33mCould not download @jupyterlab/core-meta %s (%s); "
                        "falling back to @jupyterlab/core-meta %s from %s. Set "
                        "JPBLD_OFFLINE=1 to skip the download attempt.\n \033[0m",
                        requested_version,
                        github_error,
                        core_meta_version,
                        core_meta,
                    )
                return str(core_meta)

            msg = (
                f"Could not resolve @jupyterlab/core-meta for requested version "
                f"{requested_version!r}: not found on the npm registry "
                f"({npm_error}) or in the jupyterlab/jupyterlab GitHub repository "
                f"({github_error}), and {_no_local_core_meta_message(constraint)} "
                f"Verify that the version exists (both '4.5.7' and 'v4.5.7' are accepted)."
            )
            raise RuntimeError(msg) from github_error


def get_core_meta(
    version: str | None = None,
    ext_path: str | os.PathLike[str] | None = None,
    logger: logging.Logger | None = None,
) -> str:
    """Return the path to the core package JSON, downloading it if needed."""
    if version is not None:
        # Accept both "vX.Y.Z" and "X.Y.Z" for an explicitly requested version, as
        # well as npm range specifiers such as "4", "4.5" or "^4.3.6 || ^3.6.8".
        constraint = _normalize_version(version)
        used_fallback_resolution = False
    else:
        installed_core_meta, constraint, used_fallback_resolution = (
            _resolve_version_without_installed_core_meta(ext_path, logger)
        )
        if installed_core_meta is not None:
            return installed_core_meta
    requested_version = _expand_partial_version(_range_lower_bound(constraint) or constraint)

    cache_root = _home_dir() / ".cache" / "jupyterlab_builder" / "core"
    cached_file = _get_cached_core_meta_file(cache_root, requested_version)
    if cached_file is not None:
        return str(cached_file)

    if _is_offline():
        return _offline_core_meta(
            constraint,
            used_fallback_resolution,
            logger,
            cache_root=cache_root,
        )

    return _download_core_meta(
        cache_root,
        requested_version,
        constraint,
        used_fallback_resolution,
        logger,
    )


def _resolve_version_without_installed_core_meta(
    ext_path: str | os.PathLike[str] | None,
    logger: logging.Logger | None,
) -> tuple[str | None, str, bool]:
    """Resolve a version constraint when no explicit `version` was given.

    Returns `(installed_core_meta_path, constraint, used_fallback_resolution)`, where
    `constraint` is an npm range such as "^4.0.0", or "latest". If
    `installed_core_meta_path` is not None, the caller should return it directly and
    ignore the other two values.
    """
    if ext_path is None:
        return None, "latest", True

    resolved_ext_path = Path(ext_path).resolve()
    installed_core_meta = _get_installed_core_meta(resolved_ext_path)
    if installed_core_meta is not None:
        return installed_core_meta, "", False

    legacy_spec = _legacy_builder_marker_spec(resolved_ext_path)
    if legacy_spec is not None:
        legacy_version = _range_lower_bound(legacy_spec)
        if logger:
            logger.warning(
                "\033[33m@jupyterlab/core-meta was not found in node_modules. This "
                "extension declares a devDependency on %s@%s, which is a legacy package "
                "so core-meta %s will be used instead of the latest release. "
                " To avoid this, add @jupyter/builder as a devDependency instead "
                "of %s.\n \033[0m",
                _LEGACY_BUILDER_MARKER,
                legacy_version,
                legacy_version,
                _LEGACY_BUILDER_MARKER,
            )
        return None, legacy_spec, False

    if logger:
        logger.warning(
            "\033[33m@jupyterlab/core-meta was not found in node_modules, "
            "so a network download will be used as a fallback. To avoid this, "
            "add @jupyter/builder as a devDependency instead of "
            "@jupyterlab/builder.\n \033[0m",
        )
    return None, "latest", True


def _legacy_builder_marker_spec(ext_path: Path) -> str | None:
    """Return the extension's own `@jupyterlab/builder` version range, if declared.

    Returns None if the marker isn't declared, the spec is a local path/workspace
    spec rather than a real version range, or `package.json` can't be read.
    """
    try:
        with (ext_path / "package.json").open() as fid:
            ext_data = json.load(fid)
    except (OSError, ValueError):
        return None
    version_spec = ext_data.get("devDependencies", {}).get(
        _LEGACY_BUILDER_MARKER,
    ) or ext_data.get("dependencies", {}).get(_LEGACY_BUILDER_MARKER)
    if not isinstance(version_spec, str) or "/" in version_spec:
        return None
    if _range_lower_bound(version_spec) is None:
        return None
    return version_spec.strip()


def _legacy_builder_marker_version(ext_path: Path) -> str | None:
    """Return the version the extension's `@jupyterlab/builder` range starts at, if any."""
    spec = _legacy_builder_marker_spec(ext_path)
    return _range_lower_bound(spec) if spec is not None else None


def _normalize_version(version: str) -> str:
    """Strip a leading 'v' from a numeric version so 'vX.Y.Z' and 'X.Y.Z' are equivalent."""
    return version[1:] if re.match(r"v\d", version) else version


def _range_lower_bound(spec: str) -> str | None:
    """Reduce an npm version range to the single version it should be resolved against.

    npm ranges can name more than one version: a union ("^4.3.6 || ^3.6.8"), a compound
    range (">=4.3.6 <5.0.0") or a hyphen range ("4.1.0 - 4.5.0"). None of those can be
    fetched from the registry or a git tag, so the highest alternative is selected — a
    build should target the newest JupyterLab the extension claims to support — and
    reduced to a single requestable version by `_alternative_bounds`.

    Returns None when the specifier names no version at all, e.g. "latest", a branch
    name, or "workspace:*".
    """
    candidates = [
        bounds for alternative in spec.split("||") if (bounds := _alternative_bounds(alternative))
    ]
    if not candidates:
        return None
    # Alternatives are ranked by the version each one starts at, but it is the
    # requestable form of the winning alternative that gets resolved.
    _, requested_version = max(candidates, key=lambda bounds: _semver_key(bounds[0]))
    return requested_version


def _alternative_bounds(alternative: str) -> tuple[str, str] | None:
    """Return `(lower_bound, requested_version)` for one union-free npm range.

    The leading token is the lower bound for every range form npm accepts — "^4.5.7",
    ">=4.5.7 <5.0.0" and "4.1.0 - 4.5.0" all start at the version they allow least of.
    That bound is what alternatives are ranked against each other by.

    The version actually requested differs from it only for a caret, which admits every
    later patch release: "^4.5.7" is requested as "4.5.x". Both the npm registry and the
    git tag list resolve a wildcard to its highest match, so the caret selects the newest
    patch it allows behaving like the ">=4.5.7".

    Returns None if the alternative holds no version-like token.
    """
    for token in alternative.split():
        version = _normalize_version(re.sub(r"^[\^~<>=\s]+", "", token))
        if not re.match(r"\d", version):
            continue
        if token.startswith("^"):
            return version, re.sub(r"^(\d+\.\d+)\.\d+.*$", r"\1.x", version)
        return version, version
    return None


def _expand_partial_version(version: str) -> str:
    """Expand a partial npm version specifier into an explicit wildcard range.

    npm treats an omitted trailing component as a wildcard, so "4" means 4.x.x and
    "4.5" means 4.5.x. Such a specifier is not a concrete version, so neither the npm
    registry nor a jupyterlab/jupyterlab git tag can be looked up with it directly;
    expanding it to the wildcard form lets the range resolvers pick the highest
    matching release instead. A bare wildcard ("*", "x") means "any version" and is
    mapped to "latest". Concrete versions ("4.5.7", "4.6.0-alpha.4") and non-numeric
    specifiers ("latest", "main") are returned unchanged.
    """
    if not _NUMERIC_OR_WILDCARD_SPEC.fullmatch(version):
        return version
    parts = ["x" if part in {"x", "X", "*"} else part for part in version.split(".")]
    parts.extend(["x"] * (3 - len(parts)))
    if parts[0] == "x":
        return "latest"
    # Anything following a wildcard component is unconstrained too, so "4.x.7"
    # is really 4.x.x.
    if "x" in parts:
        first_wildcard = parts.index("x")
        parts[first_wildcard:] = ["x"] * (len(parts) - first_wildcard)
    return ".".join(parts)


def _major_minor(version: str) -> str | None:
    match = re.match(r"\d+\.\d+", version)
    return match.group(0) if match else None


def _check_matches_installed_jupyterlab(
    core_meta_version: str,
    used_fallback_resolution: bool,
    logger: logging.Logger | None = None,
) -> None:
    """Fail fast if a fallback-resolved core-meta version doesn't match installed jupyterlab."""
    if not used_fallback_resolution:
        return
    try:
        jupyterlab_version = installed_version("jupyterlab")
    except PackageNotFoundError:
        return
    if _major_minor(core_meta_version) != _major_minor(jupyterlab_version):
        msg = (
            f"building against {core_meta_version} metadata but jupyterlab "
            f"{jupyterlab_version} is installed"
        )
        if logger:
            logger.error("\033[31m%s\n \033[0m", msg)
        raise RuntimeError(msg)


def _github_ref(version: str) -> str:
    """Map a resolved version to its jupyterlab/jupyterlab git ref.

    Numeric releases are published as git tags. Stable releases are tagged like
    'v4.5.7', while npm-style prereleases such as '4.6.0-alpha.4' correspond to
    the PEP 440 tag form JupyterLab uses, 'v4.6.0a4'. Branch names such as
    'main' (and other non-numeric refs) are used verbatim.
    """
    if not re.match(r"\d", version):
        return version
    release, separator, prerelease = version.partition("-")
    if separator:
        # Translate npm prerelease identifiers (alpha.4 / beta.1 / rc.2) to the
        # PEP 440 form JupyterLab tags use (a4 / b1 / rc2).
        prerelease = re.sub(r"alpha\.?", "a", prerelease)
        prerelease = re.sub(r"beta\.?", "b", prerelease)
        prerelease = re.sub(r"rc\.", "rc", prerelease)
        version = release + prerelease
    return f"v{version}"


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
        data = _http_get(f"{JPBLD_NPM_URL}/@jupyterlab/core-meta/latest")
        latest_version = json.loads(data).get("version")
        if not isinstance(latest_version, str) or not latest_version:
            msg = "Failed to resolve latest @jupyterlab/core-meta version from npm"
            raise urllib.error.URLError(msg)
        return latest_version

    if _is_wildcard_version(version):
        return _resolve_wildcard_npm_version(version)

    return version  # Concrete version like "4.2.5" — use directly


def _resolve_wildcard_npm_version(version: str) -> str:
    """Fetch the highest published npm version matching a wildcard range like '4.5.x'.

    Raises urllib.error.URLError if no matching version is found.
    """
    data = _http_get(
        f"{JPBLD_NPM_URL}/@jupyterlab/core-meta",
        headers={"Accept": "application/vnd.npm.install-v1+json"},
    )
    all_versions: list[str] = list(json.loads(data).get("versions", {}).keys())

    # Build a regex from the wildcard pattern, e.g. "4.5.x" → r"^4\.5\.\d+(-.+)?$"
    # The (-.+)? suffix matches pre-release identifiers like -alpha.3, -beta.1, -rc.2
    escaped = re.escape(version)
    wildcard_pattern = re.sub(r"x", r"\\d+", escaped, flags=re.IGNORECASE)
    pattern = "^" + wildcard_pattern + r"(-.+)?$"

    matching = [v for v in all_versions if re.match(pattern, v)]
    if not matching:
        msg = f"No published @jupyterlab/core-meta versions match range '{version}'"
        raise urllib.error.URLError(msg)

    return max(matching, key=_semver_key)


def _semver_key(v: str) -> tuple[tuple[int, ...], int, tuple[tuple[int, int, str], ...]]:
    release, _, prerelease = v.partition("-")
    numeric = tuple(int(p) for p in release.split(".") if p.isdigit())
    # Stable releases sort higher than pre-releases of the same version.
    return (numeric, 0 if prerelease else 1, _prerelease_key(prerelease))


def _prerelease_key(prerelease: str) -> tuple[tuple[int, int, str], ...]:
    """Order the dot-separated identifiers of a pre-release by semver precedence.

    Each identifier becomes `(is_alphanumeric, number, text)` so that the series it
    names is compared before the iteration within it: 'alpha.5' < 'beta.0' < 'rc.0'.
    """
    return tuple(
        (0, int(identifier), "") if identifier.isdigit() else (1, 0, identifier)
        for identifier in prerelease.split(".")
        if identifier
    )


def _resolve_github_version(version: str) -> str:
    """Resolve an abstract version specifier to a concrete jupyterlab/jupyterlab git ref.

    "latest" and wildcards (e.g. "4.5.x") have no single git ref, so they are resolved
    to a concrete tag from the GitHub tag list. Anything else is returned as-is.
    """
    if version == "latest":
        return _resolve_latest_github_version()
    if _is_wildcard_version(version):
        return _resolve_wildcard_github_version(version)
    return version


def _resolve_latest_github_version() -> str:
    """Resolve the latest stable jupyterlab/jupyterlab release tag from GitHub.

    Used as a fallback when npm cannot be reached to resolve the "latest" dist-tag.
    GitHub's "latest release" already excludes prereleases and drafts, mirroring
    npm's "latest" semantics.
    """
    data = _http_get(_GITHUB_LATEST_RELEASE_API_URL)
    release = json.loads(data)
    tag_name = release.get("tag_name") if isinstance(release, dict) else None
    if not isinstance(tag_name, str) or not tag_name:
        msg = "Failed to resolve latest jupyterlab/jupyterlab release from GitHub"
        raise urllib.error.URLError(msg)
    return _normalize_version(tag_name)


def _resolve_wildcard_github_version(version: str) -> str:
    """Resolve a wildcard range like '4.5.x' to the highest matching git tag.

    JupyterLab publishes stable releases as git tags (e.g. 'v4.5.9') that may
    predate @jupyterlab/core-meta on npm, so wildcards that npm cannot satisfy
    are resolved here against the jupyterlab/jupyterlab tag list.

    Raises urllib.error.URLError if no matching tag is found.
    """
    escaped = re.escape(version)
    wildcard_pattern = re.sub(r"x", r"\\d+", escaped, flags=re.IGNORECASE)
    pattern = re.compile("^" + wildcard_pattern + r"$")

    matching: list[str] = []
    for page in range(1, _MAX_GITHUB_TAG_PAGES + 1):
        data = _http_get(f"{_GITHUB_TAGS_API_URL}?per_page=100&page={page}")
        tags = json.loads(data)
        if not tags:
            break
        page_matches = [
            normalized
            for tag in tags
            if (normalized := _normalize_version(tag.get("name", ""))) and pattern.match(normalized)
        ]
        # Tags are returned newest-first, so once matches stop appearing
        # (after they have started) the rest are older and can be skipped.
        if matching and not page_matches:
            break
        matching.extend(page_matches)

    if not matching:
        msg = f"No jupyterlab/jupyterlab git tags match range '{version}'"
        raise urllib.error.URLError(msg)

    return max(matching, key=_semver_key)


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
    metadata = json.loads(_http_get(f"{JPBLD_NPM_URL}/@jupyterlab/core-meta/{version}"))
    try:
        tarball_url = metadata["dist"]["tarball"]
    except (KeyError, TypeError) as exc:
        msg = f"Unexpected registry metadata for {version}: {exc}"
        raise urllib.error.URLError(msg) from exc
    tarball_data = _http_get(tarball_url, timeout=20)
    with tarfile.open(fileobj=io.BytesIO(tarball_data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "package/core.package.json":
                if not member.isfile():
                    msg = "core.package.json entry is not a regular file"
                    raise urllib.error.URLError(msg)
                if member.size > _MAX_CORE_META_BYTES:
                    msg = f"core.package.json entry exceeds size limit ({member.size} bytes)"
                    raise urllib.error.URLError(msg)
                f = tar.extractfile(member)
                if f:
                    destination.write_bytes(f.read(_MAX_CORE_META_BYTES))
                    return
    msg = f"core.package.json not found in tarball for {version}"
    raise urllib.error.URLError(msg)


def _download_github_core_meta(version: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{JPBLD_RAW_GITHUB_URL}/jupyterlab/jupyterlab/{version}/jupyterlab/staging/package.json"
    destination.write_bytes(_http_get(url))


def _get_installed_core_meta(ext_path: Path) -> str | None:
    if not (ext_path / "node_modules").exists() and not _is_offline():
        subprocess.check_call(["jlpm"], cwd=ext_path)  # noqa: S607

    target = ext_path
    while True:
        core_meta_path = target / "node_modules" / "@jupyterlab" / "core-meta"
        if (core_meta_path / "core.package.json").exists():
            return str(core_meta_path / "core.package.json")
        if target.parent == target:
            return None
        target = target.parent
