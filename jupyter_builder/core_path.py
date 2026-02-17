from pathlib import Path

import requests


def get_core_staging(version: str = "main") -> str:
    """
    Fetch and cache JupyterLab core staging metadata.
    Returns path to the cached staging directory.
    """

    cache_root = Path.home() / ".cache" / "jupyterlab_builder" / "core"
    staging_path = cache_root / version

    package_json_path = staging_path / "package.json"

    # If already cached, reuse
    if package_json_path.exists():
        return str(staging_path)

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
    return str(staging_path)
