# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from jupyter_builder.extension_commands.build import BuildLabExtensionApp
from jupyter_builder.extension_commands.watch import WatchLabExtensionApp


@pytest.mark.parametrize("app_class", [BuildLabExtensionApp, WatchLabExtensionApp])
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([".", "--development"], {"development": True, "source_map": False}),
        ([".", "--source-map"], {"source_map": True}),
        (["--development", "False", "."], {"development": False}),
        (["--source-map", "True", "."], {"source_map": True}),
        # `jlpm run build --development` appends the bare flag after the path.
        (["--development", "True", ".", "--development"], {"development": True}),
    ],
)
def test_boolean_options_work_as_flags_and_aliases(app_class, argv, expected):
    """Boolean options accept a value or none at all, in any position."""
    app = app_class()
    app.parse_command_line(argv)
    for name, value in expected.items():
        assert getattr(app, name) is value
    assert app.extra_args == ["."]
