"""JupyterLab command handler"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import itertools
import logging
from jupyterlab.semver import Range, gt, gte, lt, lte
from traitlets import Bool, HasTraits, Instance, List, Unicode, default
from .coreconfig import CoreConfig
from threading import Event

# Default Yarn registry used in default yarn.lock
YARN_DEFAULT_REGISTRY = "https://registry.yarnpkg.com"




def _test_overlap(spec1, spec2, drop_prerelease1=False, drop_prerelease2=False):
    """Test whether two version specs overlap.

    Returns `None` if we cannot determine compatibility,
    otherwise whether there is an overlap
    """
    cmp = _compare_ranges(
        spec1, spec2, drop_prerelease1=drop_prerelease1, drop_prerelease2=drop_prerelease2
    )
    if cmp is None:
        return
    return cmp == 0

def _compare_ranges(spec1, spec2, drop_prerelease1=False, drop_prerelease2=False):  # noqa
    """Test whether two version specs overlap.

    Returns `None` if we cannot determine compatibility,
    otherwise return 0 if there is an overlap, 1 if
    spec1 is lower/older than spec2, and -1 if spec1
    is higher/newer than spec2.
    """
    # Test for overlapping semver ranges.
    r1 = Range(spec1, True)
    r2 = Range(spec2, True)

    # If either range is empty, we cannot verify.
    if not r1.range or not r2.range:
        return

    # Set return_value to a sentinel value
    return_value = False

    # r1.set may be a list of ranges if the range involved an ||, so we need to test for overlaps between each pair.
    for r1set, r2set in itertools.product(r1.set, r2.set):
        x1 = r1set[0].semver
        x2 = r1set[-1].semver
        y1 = r2set[0].semver
        y2 = r2set[-1].semver

        if x1.prerelease and drop_prerelease1:
            x1 = x1.inc("patch")

        if y1.prerelease and drop_prerelease2:
            y1 = y1.inc("patch")

        o1 = r1set[0].operator
        o2 = r2set[0].operator

        # We do not handle (<) specifiers.
        if o1.startswith("<") or o2.startswith("<"):
            continue

        # Handle single value specifiers.
        lx = lte if x1 == x2 else lt
        ly = lte if y1 == y2 else lt
        gx = gte if x1 == x2 else gt
        gy = gte if x1 == x2 else gt

        # Handle unbounded (>) specifiers.
        def noop(x, y, z):
            return True

        if x1 == x2 and o1.startswith(">"):
            lx = noop
        if y1 == y2 and o2.startswith(">"):
            ly = noop

        # Check for overlap.
        if (
            gte(x1, y1, True)
            and ly(x1, y2, True)
            or gy(x2, y1, True)
            and ly(x2, y2, True)
            or gte(y1, x1, True)
            and lx(y1, x2, True)
            or gx(y2, x1, True)
            and lx(y2, x2, True)
        ):
            # if we ever find an overlap, we can return immediately
            return 0

        if gte(y1, x2, True):
            if return_value is False:
                # We can possibly return 1
                return_value = 1
            elif return_value == -1:
                # conflicting information, so we must return None
                return_value = None
            continue

        if gte(x1, y2, True):
            if return_value is False:
                return_value = -1
            elif return_value == 1:
                # conflicting information, so we must return None
                return_value = None
            continue

        msg = "Unexpected case comparing version ranges"
        raise AssertionError(msg)

    if return_value is False:
        return_value = None
    return return_value


#------------------------------------------------------------------------
# base_extension_app . commands


class AppOptions(HasTraits):
    """Options object for build system"""

    def __init__(self, logger=None, core_config=None, **kwargs):
        if core_config is not None:
            kwargs["core_config"] = core_config
        if logger is not None:
            kwargs["logger"] = logger

        # use the default if app_dir is empty
        if "app_dir" in kwargs and not kwargs["app_dir"]:
            kwargs.pop("app_dir")

        super().__init__(**kwargs)

    app_dir = Unicode(help="The application directory")

    use_sys_dir = Bool(
        True,
        help=("Whether to shadow the default app_dir if that is set to a non-default value"),
    )

    logger = Instance(logging.Logger, help="The logger to use")

    core_config = Instance(CoreConfig, help="Configuration for core data")

    kill_event = Instance(Event, args=(), help="Event for aborting call")

    labextensions_path = List(
        Unicode(), help="The paths to look in for prebuilt JupyterLab extensions"
    )

    registry = Unicode(help="NPM packages registry URL")

    splice_source = Bool(False, help="Splice source packages into app directory.")

    skip_full_build_check = Bool(
        False,
        help=(
            "If true, perform only a quick check that the lab build is up to date."
            " If false, perform a thorough check, which verifies extension contents."
        ),
    )

    @default("logger")
    def _default_logger(self):
        return logging.getLogger("jupyterlab")

    # These defaults need to be federated to pick up
    # any changes to env vars:
    @default("app_dir")
    def _default_app_dir(self):
        return get_app_dir()

    @default("core_config")
    def _default_core_config(self):
        return CoreConfig()

    @default("registry")
    def _default_registry(self):
        config = _yarn_config(self.logger)["yarn config"]
        return config.get("registry", YARN_DEFAULT_REGISTRY)
    
