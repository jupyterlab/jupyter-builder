# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
from traitlets import Bool, Unicode, default, List, Instance
from jupyterlab.labapp import LabApp
from jupyterlab.commands import build
from .debug_log_file_mixin import DebugLogFileMixin

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0.0"
LABEXTENSION_COMMAND_WARNING = "Warning"


class CoreConfig:
    pass

class BaseExtensionApp(LabApp, DebugLogFileMixin):
    version = VERSION
    name = "lab"

    # Not configurable!
    core_config = Instance(CoreConfig, allow_none=True)

    app_dir = Unicode("", config=True, help="The app directory to target")

    should_build = Bool(True, config=True, help="Whether to build the app after the action")

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

    should_clean = Bool(
        False,
        config=True,
        help="Whether temporary files should be cleaned up after building jupyterlab",
    )

    splice_source = Bool(False, config=True, help="Splice source packages into app directory.")

    labextensions_path = List(
        Unicode(),
        help="The standard paths to look in for prebuilt JupyterLab extensions",
    )

    @default("labextensions_path")
    def _default_labextensions_path(self):
        lab = LabApp()
        lab.load_config_file()
        return lab.extra_labextensions_path + lab.labextensions_path

    # @default("splice_source")
    # def _default_splice_source(self):
    #     version = get_app_version(AppOptions(app_dir=self.app_dir))
    #     return version.endswith("-spliced")

    def start(self):
        if self.app_dir and self.app_dir.startswith(HERE):
            msg = "Cannot run lab extension commands in core app"
            raise ValueError(msg)
        with self.debug_logging():
            ans = self.run_task()
            if ans and self.should_build:
                production = None if self.dev_build is None else not self.dev_build
                # app_options = AppOptions(
                #     app_dir=self.app_dir,
                #     logger=self.log,
                #     core_config=self.core_config,
                #     splice_source=self.splice_source,
                # )
                build(
                    clean_staging=self.should_clean,
                    production=production,
                    minimize=self.minimize,
                    #app_options=app_options,
                )

    def run_task(self):
        pass

    def deprecation_warning(self, msg):
        return self.log.warning(
            "\033[33m(Deprecated) %s\n\n%s \033[0m", msg, LABEXTENSION_COMMAND_WARNING
        )

    def _log_format_default(self):
        """A default format for messages"""
        return "%(message)s"
