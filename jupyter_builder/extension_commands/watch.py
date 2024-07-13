# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os

from traitlets import Bool, Unicode

from ..base_extension_app import BaseExtensionApp
from ..federated_extensions import watch_labextension
from ..core_path import default_core_path

HERE = os.path.dirname(os.path.abspath(__file__))


class WatchLabExtensionApp(BaseExtensionApp):
    description = "(developer) Watch labextension"

    development = Bool(True, config=True, help="Build in development mode")

    source_map = Bool(False, config=True, help="Generate source maps")

    core_path = Unicode(
        default_core_path(),
        config=True,
        help="Directory containing core application package.json file",
    )

    aliases = {
        "core-path": "WatchLabExtensionApp.core_path",
        "development": "WatchLabExtensionApp.development",
        "source-map": "WatchLabExtensionApp.source_map",
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
            core_path=self.core_path or None,
        )


def main():
    app = WatchLabExtensionApp()
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()
