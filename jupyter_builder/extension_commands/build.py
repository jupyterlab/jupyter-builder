# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os

from traitlets import Bool, Unicode

from ..base_extension_app import BaseExtensionApp
from ..core_path import default_core_path
from ..federated_extensions import build_labextension

HERE = os.path.dirname(os.path.abspath(__file__))


class BuildLabExtensionApp(BaseExtensionApp):
    description = "(developer) Build labextension"

    static_url = Unicode("", config=True, help="Sets the url for static assets when building")

    development = Bool(False, config=True, help="Build in development mode")

    source_map = Bool(False, config=True, help="Generate source maps")

    core_path = Unicode(
        default_core_path(),
        config=True,
        help="Directory containing core application package.json file",
    )

    aliases = {
        "static-url": "BuildLabExtensionApp.static_url",
        "development": "BuildLabExtensionApp.development",
        "source-map": "BuildLabExtensionApp.source_map",
        "core-path": "BuildLabExtensionApp.core_path",
    }

    def run_task(self):
        self.extra_args = self.extra_args or [os.getcwd()]
        build_labextension(
            self.extra_args[0],
            logger=self.log,
            development=self.development,
            static_url=self.static_url or None,
            source_map=self.source_map,
            core_path=self.core_path or None,
        )


def main():
    app = BuildLabExtensionApp()
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()
