

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

    # Not configurable!
    #core_config = Instance(CoreConfig, allow_none=True)

    app_dir = Unicode("", config=True, help="The app directory to target")

    # should_build = Bool(True, config=True, help="Whether to build the app after the action")

    dev_build = Bool(
        None,
        allow_none=True,
        config=True,
        help="Whether to build in dev mode. Defaults to True (dev mode) if there are any locally linked extensions, else defaults to False (production mode).",
    )

    minimize = Bool(
        True,
        config=True,
        help="Whether to minimize a production build (defaults to True).",
    )

    # should_clean = Bool(
    #     False,
    #     config=True,
    #     help="Whether temporary files should be cleaned up after building jupyterlab",
    # )

    # splice_source = Bool(False, config=True, help="Splice source packages into app directory.")

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

    @default("splice_source")
    def _default_splice_source(self):
        # version = get_app_version(AppOptions(app_dir=self.app_dir))
        # return version.endswith("-spliced")
        return "Ronan"

    def start(self):
        if self.app_dir and self.app_dir.startswith(HERE):
            msg = "Cannot run lab extension commands in core app"
            raise ValueError(msg)
        with self.debug_logging():
            ans = self.run_task()
            # if ans and self.should_build:
            #     production = None if self.dev_build is None else not self.dev_build
            #     app_options = AppOptions(
            #         app_dir=self.app_dir,
            #         logger=self.log,
            #         core_config=self.core_config,
            #         splice_source=self.splice_source,
            #     )
            #     build(
            #         clean_staging=self.should_clean,
            #         production=production,
            #         minimize=self.minimize,
            #         app_options=app_options,
            #     )

    def run_task(self):
        pass

    def deprecation_warning(self, msg):
        return self.log.warning(
            "\033[33m(Deprecated) %s\n\n%s \033[0m", msg, LABEXTENSION_COMMAND_WARNING
        )

    def _log_format_default(self):
        """A default format for messages"""
        return "%(message)s"