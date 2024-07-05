"""Jupyter LabExtension Entry Points."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations
import os
from copy import copy

from jupyter_core.application import JupyterApp, base_aliases, base_flags
from jupyter_core.paths import jupyter_path
from traitlets import List, Unicode, default

from .debug_log_file_mixin import DebugLogFileMixin

HERE = os.path.dirname(os.path.abspath(__file__))


# from .federated_labextensions import build_labextension, develop_labextension_py, watch_labextension

flags = dict(base_flags)

develop_flags = copy(flags)
develop_flags["overwrite"] = (
    {"DevelopLabExtensionApp": {"overwrite": True}},
    "Overwrite files",
)

aliases = dict(base_aliases)
aliases["debug-log-path"] = "DebugLogFileMixin.debug_log_path"

# VERSION = get_app_version()
VERSION = 1


class BaseExtensionApp(JupyterApp, DebugLogFileMixin):
    version = VERSION
    flags = flags
    aliases = aliases
    name = "lab"

    labextensions_path = List(
        Unicode(),
        help="The standard paths to look in for prebuilt JupyterLab extensions",
    )

    # @default("labextensions_path")
    # def _default_labextensions_path(self):
    # lab = LabApp()
    # lab.load_config_file()
    # return lab.extra_labextensions_path + lab.labextensions_path
    @default("labextensions_path")
    def _default_labextensions_path(self) -> list[str]:
        return jupyter_path("labextensions")

    def start(self):
        with self.debug_logging():
            self.run_task()

    def run_task(self):
        pass

    def _log_format_default(self):
        """A default format for messages"""
        return "%(message)s"
