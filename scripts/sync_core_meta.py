# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Sync jupyter_builder/core.package.json with @jupyterlab/core-meta in node_modules."""

from __future__ import annotations

import argparse
import filecmp
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

    if check:
        if not TARGET.exists() or not filecmp.cmp(SOURCE, TARGET, shallow=False):
            print(
                f"Error: {TARGET} is out of date with {SOURCE}.\n"
                "Run 'jlpm run sync:core-meta' or 'python scripts/sync_core_meta.py' to update it.",
                file=sys.stderr,
            )
            return 1
        print("jupyter_builder/core.package.json is up to date.")
        return 0

    shutil.copy2(SOURCE, TARGET)
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
