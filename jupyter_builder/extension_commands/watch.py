# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os

from traitlets import Bool, Unicode

from jupyter_builder.base_extension_app import BaseExtensionApp
from jupyter_builder.federated_extensions import watch_labextension

HERE = os.path.dirname(os.path.abspath(__file__))


class WatchLabExtensionApp(BaseExtensionApp):
    description = "(developer) Watch labextension"

    development = Bool(True, config=True, help="Build in development mode")

    source_map = Bool(False, config=True, help="Generate source maps")

    core_package_file = Unicode(
        "",
        config=True,
        help="Path to the core application package definition file",
    )

    core_version = Unicode(
        "main",
        config=True,
        help=(
            "Version of JupyterLab core to use when watching (ignored if core-package-file is set)"
        ),
    )

    aliases = {  # noqa: RUF012
        "core-package-file": "WatchLabExtensionApp.core_package_file",
        "development": "WatchLabExtensionApp.development",
        "source-map": "WatchLabExtensionApp.source_map",
        "core-version": "WatchLabExtensionApp.core_version",
    }

    def run_task(self):
        self.extra_args = self.extra_args or [os.getcwd()]
        labextensions_path = self.labextensions_path
        watch_labextension(
            self.extra_args[0],
            labextensions_path,
            logger=self.log,
            development=self.development,
            source_map=self.source_map,
            core_version=self.core_version or None,
            core_package_file=self.core_package_file or None,
        )


def main():
    app = WatchLabExtensionApp()
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()
