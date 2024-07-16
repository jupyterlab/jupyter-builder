# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# # Copyright (c) Jupyter Development Team.
# # Distributed under the terms of the Modified BSD License.

import sys

from jupyter_core.application import JupyterApp

from jupyter_builder.extension_commands.build import BuildLabExtensionApp
from jupyter_builder.extension_commands.develop import DevelopLabExtensionApp
from jupyter_builder.extension_commands.watch import WatchLabExtensionApp


class LabExtensionApp(JupyterApp):
    """Base jupyter labextension command entry point"""

    name = "jupyter labextension"
    # version = VERSION
    description = "Work with JupyterLab extensions"
    # examples = _EXAMPLES

    subcommands = {
        # "install": (InstallLabExtensionApp, "Install labextension(s)"),
        # "update": (UpdateLabExtensionApp, "Update labextension(s)"),
        # "uninstall": (UninstallLabExtensionApp, "Uninstall labextension(s)"),
        # "list": (ListLabExtensionsApp, "List labextensions"),
        # "link": (LinkLabExtensionApp, "Link labextension(s)"),
        # "unlink": (UnlinkLabExtensionApp, "Unlink labextension(s)"),
        # "enable": (EnableLabExtensionsApp, "Enable labextension(s)"),
        # "disable": (DisableLabExtensionsApp, "Disable labextension(s)"),
        # "lock": (LockLabExtensionsApp, "Lock labextension(s)"),
        # "unlock": (UnlockLabExtensionsApp, "Unlock labextension(s)"),
        # "check": (CheckLabExtensionsApp, "Check labextension(s)"),
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
