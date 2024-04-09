"""Utilities for installing extensions"""
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

# import logging
# import os
# import sys
import typing as t

from .jupyter_app import JupyterApp
# from jupyter_core.application import JupyterApp



class ArgumentConflict(ValueError):
    pass


_base_flags: dict[str, t.Any] = {}
_base_flags.update(JupyterApp.flags)
_base_flags.pop("y", None)
_base_flags.pop("generate-config", None)
_base_flags.update(
    {
        "user": (
            {
                "BaseExtensionApp": {
                    "user": True,
                }
            },
            "Apply the operation only for the given user",
        ),
        "system": (
            {
                "BaseExtensionApp": {
                    "user": False,
                    "sys_prefix": False,
                }
            },
            "Apply the operation system-wide",
        ),
        "sys-prefix": (
            {
                "BaseExtensionApp": {
                    "sys_prefix": True,
                }
            },
            "Use sys.prefix as the prefix for installing extensions (for environments, packaging)",
        ),
        "py": (
            {
                "BaseExtensionApp": {
                    "python": True,
                }
            },
            "Install from a Python package",
        ),
    }
)
_base_flags["python"] = _base_flags["py"]

_base_aliases: dict[str, t.Any] = {}
_base_aliases.update(JupyterApp.aliases)


