# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import sys
from traitlets.config.application import Application
from .commands.develop import DevelopLabExtensionApp
from .commands.build import BuildLabExtensionApp
from .commands.watch import WatchLabExtensionApp

class BaseExtensionApp(Application):
    name = "lab"
    version = "1.0.0"
    description = "Base application for lab extensions"

    def start(self):
        if len(self.extra_args) < 1:
            self.log.error("Please specify a command: develop, build, or watch.")
            return

        command = self.extra_args[0]
        if command == 'develop':
            DevelopLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
        elif command == 'build':
            BuildLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
        elif command == 'watch':
            WatchLabExtensionApp.launch_instance(argv=self.extra_args[1:], parent=self)
        else:
            self.log.error("Invalid command: %s. Use develop, build, or watch." % command)

if __name__ == "__main__":
    BaseExtensionApp.launch_instance()
