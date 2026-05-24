# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import hashlib
from pathlib import Path

from jupyter_builder import YARN_SHA256, YARN_VERSION
from jupyter_builder.jlpm import YARN_PATH

SEMVER_PART_COUNT = 3


def test_yarn_version_is_set():
    assert YARN_VERSION
    assert isinstance(YARN_VERSION, str)
    parts = YARN_VERSION.split(".")
    assert len(parts) == SEMVER_PART_COUNT, f"Expected semver x.y.z, got {YARN_VERSION!r}"


def test_yarn_sha256_matches_file():
    actual = hashlib.sha256(Path(YARN_PATH).read_bytes()).hexdigest()
    assert actual == YARN_SHA256, (
        f"yarn.js sha256={actual!r} does not match "
        f"YARN_SHA256={YARN_SHA256!r} — "
        "was yarn.js updated without regenerating _yarn_info?"
    )
