#!/usr/bin/env python3
"""Build the JS assets and copy lib + node_modules into jupyter_builder/static.

Run this script before building or releasing the Python package:
    python scripts/build_static.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC_DIR = ROOT / "jupyter_builder" / "static"


def main() -> None:
    subprocess.check_call(["node", str(ROOT / "jupyter_builder" / "yarn.js"), "build:lib:prod"])  # noqa S603

    lib_src = ROOT / "lib"
    node_modules_src = ROOT / "node_modules"

    lib_dst = STATIC_DIR / "lib"
    node_modules_dst = STATIC_DIR / "node_modules"

    if lib_dst.exists():
        shutil.rmtree(lib_dst)
    shutil.copytree(lib_src, lib_dst)

    if node_modules_dst.exists():
        shutil.rmtree(node_modules_dst)
    shutil.copytree(node_modules_src, node_modules_dst)


if __name__ == "__main__":
    sys.exit(main())
