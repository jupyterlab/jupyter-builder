"""Helpers for resolving and installing an extension's node dependencies."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import json
import logging
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)


def find_in_node_modules(start: Path, parts: Sequence[str]) -> Path | None:
    """Return the closest directory whose ``node_modules`` contains ``parts``.

    Mirrors node module resolution: ``start`` is checked first, then each
    ancestor up to the filesystem root.

    Parameters
    ----------
    start : Path
        Directory to start searching from (usually the extension path).
    parts : Sequence[str]
        Path segments below ``node_modules``, e.g. ``("@jupyter", "builder")``.

    Returns
    -------
    Path | None
        The directory owning the matching ``node_modules``, or None if no
        ancestor contains it.

    """
    target = start
    while not target.joinpath("node_modules", *parts).exists():
        if target.parent == target:
            return None
        target = target.parent
    return target


def is_workspace_root(path: Path) -> bool:
    """Return whether ``path`` is the root of a Yarn/npm or pnpm workspace.

    A directory is a workspace root if its ``package.json`` declares a
    non-empty ``workspaces`` field (an array, or an object with ``packages``),
    or if it contains a ``pnpm-workspace.yaml`` file. An unreadable or invalid
    ``package.json`` is treated as "not a workspace root".

    Parameters
    ----------
    path : Path
        Directory to inspect.

    Returns
    -------
    bool
        True if ``path`` is a workspace root.

    """
    if (path / "pnpm-workspace.yaml").is_file():
        return True
    try:
        with (path / "package.json").open() as fid:
            data = json.load(fid)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    workspaces = data.get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    return isinstance(workspaces, list) and len(workspaces) > 0


def is_workspace_member(root: Path, ext_path: Path) -> bool:
    """Return whether ``ext_path`` is an installed member of the workspace at ``root``.

    npm and Yarn link every workspace member into the root's ``node_modules``
    under its package name, so ``ext_path`` is a member if that link resolves
    back to it. A package that only sits below ``root`` without being listed
    in its ``workspaces`` (e.g. a standalone test fixture with its own
    ``yarn.lock``) has no such link.

    Parameters
    ----------
    root : Path
        The workspace root directory.
    ext_path : Path
        The extension directory.

    Returns
    -------
    bool
        True if ``root/node_modules/<name>`` is ``ext_path``.

    """
    try:
        with (ext_path / "package.json").open() as fid:
            data = json.load(fid)
    except (OSError, ValueError):
        return False
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name:
        return False
    try:
        return (root / "node_modules" / name).samefile(ext_path)
    except OSError:
        return False


def ensure_dependencies_installed(ext_path: Path, probe: Sequence[str]) -> None:
    """Run ``jlpm`` in ``ext_path`` unless its dependencies are already available.

    The install is skipped when ``ext_path`` already has a ``node_modules``
    directory, or when ``probe`` resolves from an ancestor that is a workspace
    root and ``ext_path`` is one of its installed members (dependencies hoisted
    in a monorepo). A ``node_modules`` in an unrelated ancestor (e.g. the home
    directory) or in a workspace that ``ext_path`` doesn't belong to does not
    suppress the install.

    Parameters
    ----------
    ext_path : Path
        The extension directory.
    probe : Sequence[str]
        Path segments below ``node_modules`` of a package the caller needs,
        e.g. ``("@jupyter", "builder")``.

    Raises
    ------
    subprocess.CalledProcessError
        If ``jlpm`` fails.

    """
    if (ext_path / "node_modules").exists():
        return
    owner = find_in_node_modules(ext_path, probe)
    if owner is not None and is_workspace_root(owner) and is_workspace_member(owner, ext_path):
        logger.debug(
            "Skipping jlpm in %s: %s resolves from workspace root %s",
            ext_path,
            "/".join(probe),
            owner,
        )
        return
    subprocess.check_call(["jlpm"], cwd=ext_path)  # noqa: S607
