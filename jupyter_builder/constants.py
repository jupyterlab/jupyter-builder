# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""URL constants for jupyter-builder network fetches, overridable via environment variables."""

import os
import warnings

#: Base URL for the npm registry
JPBLD_NPM_URL: str = os.getenv("JPBLD_NPM_URL", "https://registry.npmjs.org")

#: Base GitHub URL for the jupyterlab/jupyterlab repository
JPBLD_GITHUB_URL: str = "https://github.com"

#: Base raw GitHub content URL
JPBLD_RAW_GITHUB_URL: str = "https://raw.githubusercontent.com"

if os.getenv("JPBLD_NPM_URL") is not None:
    warnings.warn(
        f"jupyter-builder: JPBLD_NPM_URL overridden to {JPBLD_NPM_URL!r}",
        UserWarning,
        stacklevel=2,
    )
