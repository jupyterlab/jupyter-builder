# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# # Copyright (c) Jupyter Development Team.
# # Distributed under the terms of the Modified BSD License.

import sys

from jupyter_core.application import JupyterApp

from jupyter_builder.extension_commands.build import BuildLabExtensionApp
from jupyter_builder.extension_commands.develop import DevelopLabExtensionApp
from jupyter_builder.extension_commands.watch import WatchLabExtensionApp

_EXAMPLES = """
jupyter-builder build                       # (developer) build a prebuilt labextension
jupyter-builder develop                     # (developer) develop a prebuilt labextension
jupyter-builder watch                       # (developer) watch a prebuilt labextension
"""


class LabExtensionApp(JupyterApp):
    """Base jupyter-builder command entry point"""

    name = "jupyter builder"
    # version = VERSION
    description = "Build JupyterLab extensions"
    examples = _EXAMPLES

    subcommands = {
        "develop": (DevelopLabExtensionApp, "(developer) Develop labextension(s)"),
        "build": (BuildLabExtensionApp, "(developer) Build labextension"),
        "watch": (WatchLabExtensionApp, "(developer) Watch labextension"),
    }

    def start(self):
        """Perform the App's functions as configured"""
        super().start()

        # The above should have called a subcommand and raised NoStart; if we
        # get here, it didn't, so we should self.log.info a message.
        subcmds = ", ".join(sorted(self.subcommands))
        self.exit(f"Please supply at least one subcommand: {subcmds}")


main = LabExtensionApp.launch_instance

if __name__ == "__main__":
    sys.exit(main())
