# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Sync jupyter_builder/core.package.json with @jupyterlab/core-meta in node_modules.

The bundled copy is jupyter-builder's last-resort core metadata for offline builds. It
must match the @jupyterlab/core-meta pinned in yarn.lock byte for byte, so it is never
edited by hand: bump @jupyterlab/core-meta, run `jlpm`, then `jlpm sync:core-meta`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "node_modules" / "@jupyterlab" / "core-meta" / "core.package.json"
TARGET = ROOT / "jupyter_builder" / "core.package.json"


def sync_core_meta(*, check: bool = False) -> int:
    """Sync or check jupyter_builder/core.package.json against node_modules."""
    if not SOURCE.exists():
        print(
            f"Source file {SOURCE} does not exist. Run jlpm install first.",
            file=sys.stderr,
        )
        return 1

    in_sync = TARGET.exists() and TARGET.read_bytes() == SOURCE.read_bytes()
    if check:
        if not in_sync:
            print(
                f"Error: {TARGET} does not match {SOURCE}.\n"
                "This file is generated from the @jupyterlab/core-meta pinned in yarn.lock "
                "and must not be edited by hand. Run 'jlpm' and then "
                "'jlpm sync:core-meta' to regenerate it.",
                file=sys.stderr,
            )
            return 1
        print(f"{TARGET.name} is in sync with @jupyterlab/core-meta.")
        return 0

    if not in_sync:
        shutil.copyfile(SOURCE, TARGET)
    print(f"Synced {SOURCE} -> {TARGET}")
    return 0


def main() -> None:
    """CLI entrypoint for sync_core_meta."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether target is in sync without modifying it",
    )
    args = parser.parse_args()
    sys.exit(sync_core_meta(check=args.check))


if __name__ == "__main__":
    main()
