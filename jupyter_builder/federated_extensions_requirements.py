"""JupyterLab Server config"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import json
import os.path as osp
from glob import iglob
from itertools import chain

# from logging import Logger
from os.path import join as pjoin
from typing import Any

# import json5  # type:ignore[import-untyped]
# from jupyter_core.paths import SYSTEM_CONFIG_PATH, jupyter_config_dir, jupyter_path
# from jupyter_server.services.config.manager import ConfigManager, recursive_update
# from jupyter_server.utils import url_path_join as ujoin
# from traitlets import Bool, HasTraits, List, Unicode, default

# -----------------------------------------------------------------------------
# Module globals
# -----------------------------------------------------------------------------

DEFAULT_TEMPLATE_PATH = osp.join(osp.dirname(__file__), "templates")


def get_package_url(data: dict[str, Any]) -> str:
    """Get the url from the extension data"""
    # homepage, repository  are optional
    if "homepage" in data:
        url = data["homepage"]
    elif "repository" in data and isinstance(data["repository"], dict):
        url = data["repository"].get("url", "")
    else:
        url = ""
    return url


def get_federated_extensions(labextensions_path: list[str]) -> dict[str, Any]:
    """Get the metadata about federated extensions"""
    federated_extensions = {}
    for ext_dir in labextensions_path:
        # extensions are either top-level directories, or two-deep in @org directories
        for ext_path in chain(
            iglob(pjoin(ext_dir, "[!@]*", "package.json")),
            iglob(pjoin(ext_dir, "@*", "*", "package.json")),
        ):
            with open(ext_path, encoding="utf-8") as fid:
                pkgdata = json.load(fid)
            if pkgdata["name"] not in federated_extensions:
                data = dict(
                    name=pkgdata["name"],
                    version=pkgdata["version"],
                    description=pkgdata.get("description", ""),
                    url=get_package_url(pkgdata),
                    ext_dir=ext_dir,
                    ext_path=osp.dirname(ext_path),
                    is_local=False,
                    dependencies=pkgdata.get("dependencies", dict()),
                    jupyterlab=pkgdata.get("jupyterlab", dict()),
                )

                # Add repository info if available
                if "repository" in pkgdata and "url" in pkgdata.get("repository", {}):
                    data["repository"] = dict(url=pkgdata.get("repository").get("url"))

                install_path = osp.join(osp.dirname(ext_path), "install.json")
                if osp.exists(install_path):
                    with open(install_path, encoding="utf-8") as fid:
                        data["install"] = json.load(fid)
                federated_extensions[data["name"]] = data
    return federated_extensions
