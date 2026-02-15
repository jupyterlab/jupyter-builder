# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import tempfile
from pathlib import Path

import requests


def create_temp_core_path(core_version=None) -> str:
    """
    Download JupyterLab staging/package.json into a temporary directory
    and return the path to that staging directory.
    """
    version = core_version or "main"
    url = (
        "https://raw.githubusercontent.com/"
        f"jupyterlab/jupyterlab/{version}/"
        "jupyterlab/staging/package.json"
    )

    # Create persistent temporary directory
    tmpdir = tempfile.mkdtemp(prefix="jupyterlab-staging-")
    staging_path = Path(tmpdir)

    # Download package.json
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    (staging_path / "package.json").write_bytes(response.content)

    return str(staging_path)
