# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Yarn version and integrity information for the vendored yarn.js."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_yarn_js = Path(__file__).resolve().parent / "yarn.js"
_yarn_bytes = _yarn_js.read_bytes()

# Minified yarn berry embeds the version as: YarnVersion:()=>VarName ... var VarName="x.y.z"
_match = re.search(rb"YarnVersion:\(\)=>(\w+)", _yarn_bytes)
if _match:
    _var = re.escape(_match.group(1))
    _match = re.search(rb"var " + _var + rb'="([^"]+)"', _yarn_bytes)

# Fallback for non-minified builds: YARN_VERSION = "x.y.z"
if not _match:
    _match = re.search(rb'YARN_VERSION\s*=\s*["\']([^"\']+)["\']', _yarn_bytes)

if not _match:
    msg = "Could not extract YARN_VERSION from vendored yarn.js"
    raise RuntimeError(msg)

YARN_VERSION: str = _match.group(1).decode()
YARN_SHA256: str = hashlib.sha256(_yarn_bytes).hexdigest()
