# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

# # Copyright (c) Jupyter Development Team.
# # Distributed under the terms of the Modified BSD License.

import sys
from traitlets.config.application import Application
from jupyter_builder.extension_commands.develop import DevelopLabExtensionApp
from jupyter_core.application import JupyterApp
# # from .commands.build import BuildLabExtensionApp
# # from .commands.watch import WatchLabExtensionApp

# class BaseExtensionApp(Application):
#     name = "lab"
#     version = "1.0.0"
#     description = "Base application for lab extensions"

#     def start(self):
#         if len(self.extra_args) < 1:
#             self.log.error("Please specify a command: develop, build, or watch.")
#             return

#         command = self.extra_args[0]
#         if command == 'develop':
#             DevelopLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
#         elif command == 'build':
#             BuildLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
#         elif command == 'watch':
#             WatchLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
#         else:
#             self.log.error("Invalid command: %s. Use develop, build, or watch." % command)

# if __name__ == "__main__":
#     BaseExtensionApp.launch_instance()


class LabExtensionApp(JupyterApp):
    """Base jupyter labextension command entry point"""

    name = "jupyter labextension"
    #version = VERSION
    description = "Work with JupyterLab extensions"
    #examples = _EXAMPLES

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
        # "build": (BuildLabExtensionApp, "(developer) Build labextension"),
        # "watch": (WatchLabExtensionApp, "(developer) Watch labextension"),
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