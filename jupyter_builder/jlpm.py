# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""A Jupyter-aware wrapper for the yarn package manager"""

import os
import subprocess
import sys
from shutil import which

HERE = os.path.dirname(os.path.abspath(__file__))
YARN_PATH = os.path.join(HERE, "yarn.js")


def _which_node_js(env: dict[str, str] | None = None) -> str:
    """Get the full path to Node.js executable

    Parameters
    ----------
    env: dict, optional
        The environment variables, defaults to `os.environ`.
    """
    command = "node"
    env = env or os.environ  # type:ignore[assignment]
    path = env.get("PATH") or os.defpath  # type:ignore[union-attr]
    command_with_path = which(command, path=path)

    # Allow nodejs as an alias to node.
    if command == "node" and not command_with_path:
        command = "nodejs"
        command_with_path = which("nodejs", path=path)

    if not command_with_path:
        if command in ["nodejs", "node", "npm"]:
            msg = (
                "Please install Node.js and npm before continuing installation. "
                "You may be able to install Node.js from your package manager, "
                "from conda, or directly from the Node.js website "
                "(https://nodejs.org)."
            )
            raise ValueError(msg)
        msg = f"The command was not found or was not executable: {command}."
        raise ValueError(msg)
    return os.path.abspath(command_with_path)


def _execvp_node(argv):
    """Execvp, except on Windows where it uses Popen.

    The first argument, by convention, should point to the filename
    associated with the file being executed.

    Python provides execvp on Windows, but its behavior is problematic
    (Python bug#9148).
    """
    cmd = _which_node_js()
    if os.name == "nt":
        import signal

        p = subprocess.Popen([cmd] + argv[1:])  # noqa S603
        # Don't raise KeyboardInterrupt in the parent process.
        # Set this after spawning, to avoid subprocess inheriting handler.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        p.wait()
        sys.exit(p.returncode)
    else:
        os.execvp(cmd, argv)  # noqa S606


def main(argv=None):
    """Run node and return the result."""
    # Make sure node is available.
    argv = argv or sys.argv[1:]
    _execvp_node(["node", YARN_PATH, *argv])
