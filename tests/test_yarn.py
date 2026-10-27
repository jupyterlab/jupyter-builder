# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Check the committed Yarn constants against the vendored bundle."""

import hashlib
import sys
from pathlib import Path

import pytest

from jupyter_builder import YARN_PACKAGE_MANAGER, YARN_SHA256, YARN_VERSION
from jupyter_builder._yarn_info import YARN_PATH

REGENERATE = "Run `python scripts/update_yarn_version.py` and commit the result."

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    # Appended rather than prepended: `scripts/` only needs to be reachable, and
    # putting it first would let it shadow real modules for the whole session.
    sys.path.append(str(_SCRIPTS))

try:
    import update_yarn_version
except ImportError:  # pragma: no cover - only when run outside the source tree
    update_yarn_version = None

# The generator lives in `scripts/`, which is not shipped in the wheel; the
# tests that need it are skipped when this module runs against an installation.
needs_generator = pytest.mark.skipif(
    update_yarn_version is None,
    reason="scripts/update_yarn_version.py is not importable",
)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def test_yarn_path_points_at_the_bundle():
    assert YARN_PATH.is_file(), f"vendored bundle missing at {YARN_PATH}"
    assert YARN_PATH.stat().st_size > 0, f"vendored bundle is empty at {YARN_PATH}"


def test_sha256_matches_the_bundle():
    assert _sha256(YARN_PATH) == YARN_SHA256, (
        f"YARN_SHA256 does not match {YARN_PATH}. {REGENERATE}"
    )


def test_package_manager_is_derived_from_the_version():
    assert f"yarn@{YARN_VERSION}" == YARN_PACKAGE_MANAGER


@needs_generator
def test_extract_version_matches_the_constant():
    extracted = update_yarn_version.extract_version(YARN_PATH.read_bytes())
    assert extracted == YARN_VERSION, (
        f"the bundle at {YARN_PATH} reports {extracted}, but YARN_VERSION is "
        f"{YARN_VERSION}. {REGENERATE}"
    )


@needs_generator
def test_generated_files_are_up_to_date():
    version = update_yarn_version.extract_version(YARN_PATH.read_bytes())
    stale = update_yarn_version.stale_targets(version, _sha256(YARN_PATH))
    assert stale == [], f"stale generated files: {stale}. {REGENERATE}"
