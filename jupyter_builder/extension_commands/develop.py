# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
from copy import copy

from jupyter_core.application import base_flags
from traitlets import Bool, Unicode

from jupyter_builder.base_extension_app import BaseExtensionApp
from jupyter_builder.federated_extensions import develop_labextension_py

flags = dict(base_flags)
develop_flags = copy(flags)
develop_flags["overwrite"] = (
    {"DevelopLabExtensionApp": {"overwrite": True}},
    "Overwrite files",
)


class DevelopLabExtensionApp(BaseExtensionApp):
    description = "(developer) Develop labextension"

    flags = develop_flags
    user = Bool(False, config=True, help="Whether to do a user install")
    sys_prefix = Bool(True, config=True, help="Use the sys.prefix as the prefix")
    overwrite = Bool(False, config=True, help="Whether to overwrite files")  # flags
    symlink = Bool(True, config=False, help="Whether to use a symlink")

    labextensions_dir = Unicode(
        "",
        config=True,
        help="Full path to labextensions dir (probably use prefix or user)",
    )

    def run_task(self):
        """Add config for this labextension"""
        self.extra_args = self.extra_args or [os.getcwd()]
        for arg in self.extra_args:
            develop_labextension_py(
                arg,
                user=self.user,
                sys_prefix=self.sys_prefix,
                labextensions_dir=self.labextensions_dir,
                logger=self.log,
                overwrite=self.overwrite,
                symlink=self.symlink,
            )


def main():
    app = DevelopLabExtensionApp()
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()
