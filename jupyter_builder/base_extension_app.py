

"""Jupyter LabExtension Entry Points."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import sys
from copy import copy

from jupyter_core.application import JupyterApp, base_aliases, base_flags
from traitlets import Bool, Instance, List, Unicode, default
from jupyter_core.paths import jupyter_path

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

#VERSION = get_app_version()
VERSION = 1

LABEXTENSION_COMMAND_WARNING = "Users should manage prebuilt extensions with package managers like pip and conda, and extension authors are encouraged to distribute their extensions as prebuilt packages"


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
            ans = self.run_task()

    def run_task(self):
        pass

    def deprecation_warning(self, msg):
        return self.log.warning(
            "\033[33m(Deprecated) %s\n\n%s \033[0m", msg, LABEXTENSION_COMMAND_WARNING
        )

    def _log_format_default(self):
        """A default format for messages"""
        return "%(message)s"