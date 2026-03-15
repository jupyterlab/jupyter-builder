# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import requests


@dataclass(frozen=True)
class CoreMetaLocation(os.PathLike[str]):
    path: str
    package_file: str = "package.json"

    def __fspath__(self) -> str:
        return self.path

    def __str__(self) -> str:
        return self.path


def get_core_meta(
    version: str = "main", ext_path: Optional[Union[str, os.PathLike[str]]] = None
) -> CoreMetaLocation:
    """
    Resolve JupyterLab core metadata for an extension build.

    Prefer an installed ``@jupyterlab/core-meta`` package when available.
    Otherwise, fetch and cache the staging ``package.json`` from GitHub.
    """

    if ext_path is not None:
        installed_core_meta = _get_installed_core_meta(Path(ext_path).resolve())
        if installed_core_meta is not None:
            return installed_core_meta

    cache_root = Path.home() / ".cache" / "jupyterlab_builder" / "core"
    staging_path = cache_root / version

    package_json_path = staging_path / "package.json"

    # If already cached, reuse
    if package_json_path.exists():
        return CoreMetaLocation(str(staging_path))

    # Otherwise download
    staging_path.mkdir(parents=True, exist_ok=True)

    url = (
        "https://raw.githubusercontent.com/"
        f"jupyterlab/jupyterlab/{version}/"
        "jupyterlab/staging/package.json"
    )

    r = requests.get(url, timeout=10)
    r.raise_for_status()

    package_json_path.write_bytes(r.content)
    return CoreMetaLocation(str(staging_path))


def _get_installed_core_meta(ext_path: Path) -> Optional[CoreMetaLocation]:
    if not (ext_path / "node_modules").exists():
        subprocess.check_call(["jlpm"], cwd=ext_path)  # noqa: S603 S607

    target = ext_path
    while True:
        core_meta_path = target / "node_modules" / "@jupyterlab" / "core-meta"
        if (core_meta_path / "core.package.json").exists():
            return CoreMetaLocation(str(core_meta_path), "core.package.json")
        if target.parent == target:
            return None
        target = target.parent
