# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Regenerate the vendored-yarn constants from ``jupyter_builder/yarn.js``.

``jupyter_builder/_yarn_info.py`` and ``src/yarnInfo.ts`` expose the version and
the SHA-256 of the vendored Yarn bundle as plain literals. This script is what
produces those literals; run it after replacing the bundle and commit the result:

    python scripts/update_yarn_version.py

``--check`` reports drift and exits non-zero without editing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
YARN_JS = REPO_ROOT / "jupyter_builder" / "yarn.js"
PYTHON_TARGET = REPO_ROOT / "jupyter_builder" / "_yarn_info.py"
TS_TARGET = REPO_ROOT / "src" / "yarnInfo.ts"

_CHUNK_SIZE = 1 << 20

# Minified Yarn Berry exports the version indirectly: the module map holds an
# accessor `YarnVersion:()=>Lr`, and the string itself is a `var Lr="3.5.0"`
# elsewhere in the bundle. Both halves are esbuild output details, hence the
# sanity check below and the test in tests/test_yarn.py.
_ACCESSOR_RE = re.compile(rb"YarnVersion:\(\)=>(\w+)")
_SEMVER_RE = re.compile(r"\A\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z")

# End of the matched line, tolerating CRLF checkouts.
_EOL = r"(?=\r?\n|\Z)"

# Anchored patterns for the generated literals. Each must match exactly once in
# its file; group 1 and group 2 are the surrounding text that is kept.
_TARGETS: tuple[tuple[Path, tuple[tuple[re.Pattern[str], str], ...]], ...] = (
    (
        PYTHON_TARGET,
        (
            (re.compile(r'^(YARN_VERSION: str = ")[^"]*(")' + _EOL, re.MULTILINE), "version"),
            (re.compile(r'^(YARN_SHA256: str = ")[^"]*(")' + _EOL, re.MULTILINE), "sha256"),
        ),
    ),
    (
        TS_TARGET,
        (
            (
                re.compile(r"^(export const YARN_VERSION = ')[^']*(';)" + _EOL, re.MULTILINE),
                "version",
            ),
            (
                re.compile(r"^(export const YARN_SHA256 =\r?\n  ')[^']*(';)" + _EOL, re.MULTILINE),
                "sha256",
            ),
        ),
    ),
)


def _read(path: Path) -> str:
    """Read a text file without translating its line endings."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    """Write a text file without translating its line endings."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def extract_version(data: bytes) -> str:
    """Return the Yarn version embedded in the bytes of a Yarn Berry bundle.

    Raises
    ------
    ValueError
        If the bundle does not carry a recognisable version, with a message
        naming which half of the lookup failed.

    """
    accessor = _ACCESSOR_RE.search(data)
    if accessor is None:
        msg = (
            "No `YarnVersion` export found in the bundle: the accessor pattern "
            f"{_ACCESSOR_RE.pattern!r} did not match. The bundle layout has changed; "
            "update the pattern in scripts/update_yarn_version.py."
        )
        raise ValueError(msg)

    name = accessor.group(1)
    assignment = re.search(rb"var " + re.escape(name) + rb'="([^"]+)"', data)
    if assignment is None:
        msg = (
            f"No assignment found for variable {name.decode()!r}, which the `YarnVersion` "
            "export points at. The bundle layout has changed; update the pattern in "
            "scripts/update_yarn_version.py."
        )
        raise ValueError(msg)

    version = assignment.group(1).decode()
    if not _SEMVER_RE.match(version):
        msg = (
            f"Extracted {version!r} for variable {name.decode()!r}, which is not a version "
            "number. The extraction matched the wrong thing; update the patterns in "
            "scripts/update_yarn_version.py."
        )
        raise ValueError(msg)
    return version


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _substitute(text: str, path: Path, pattern: re.Pattern[str], value: str) -> str:
    """Replace the single literal matched by ``pattern`` with ``value``."""
    count = len(pattern.findall(text))
    if count != 1:
        msg = (
            f"{path.relative_to(REPO_ROOT)}: pattern {pattern.pattern!r} matched {count} times, "
            "expected exactly 1. The generated file was edited by hand or renamed; reconcile it "
            "with scripts/update_yarn_version.py."
        )
        raise ValueError(msg)
    return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(2)}", text)


def stale_targets(version: str, sha256: str, *, write: bool = False) -> list[Path]:
    """Return the generated files whose literals differ from ``version``/``sha256``.

    With ``write=True`` the differing files are rewritten in place.
    """
    values = {"version": version, "sha256": sha256}
    stale = []
    for path, patterns in _TARGETS:
        original = _read(path)
        updated = original
        for pattern, key in patterns:
            updated = _substitute(updated, path, pattern, values[key])
        if updated != original:
            stale.append(path)
            if write:
                _write(path, updated)
    return stale


def main(argv: list[str] | None = None) -> int:
    """Update (or check) the generated Yarn constants. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Regenerate the vendored-yarn constants from jupyter_builder/yarn.js.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of rewriting the files",
    )
    args = parser.parse_args(argv)

    if not YARN_JS.is_file():
        msg = f"Vendored bundle not found: {YARN_JS}"
        raise FileNotFoundError(msg)

    version = extract_version(YARN_JS.read_bytes())
    sha256 = sha256_file(YARN_JS)

    stale = stale_targets(version, sha256, write=not args.check)

    if args.check and stale:
        names = ", ".join(str(path.relative_to(REPO_ROOT)) for path in stale)
        print(f"Out of date with jupyter_builder/yarn.js: {names}")
        print("Run `python scripts/update_yarn_version.py` and commit the result.")
        return 1

    print(f"yarn {version} ({sha256[:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
