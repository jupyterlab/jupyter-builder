"""Compare npm version ranges."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import itertools
from typing import Any

from .jupyterlab_semver import Range, SemVer, gt, gte, lt, lte


def ranges_overlap(
    spec1: str,
    spec2: str,
    drop_prerelease1: bool = False,
    drop_prerelease2: bool = False,
) -> bool | None:
    """Test whether two version specs overlap.

    Returns `None` if we cannot determine compatibility,
    otherwise whether there is an overlap
    """
    cmp = compare_ranges(
        spec1,
        spec2,
        drop_prerelease1=drop_prerelease1,
        drop_prerelease2=drop_prerelease2,
    )
    if cmp is None:
        return None
    return cmp == 0


def _branch_interval(
    comparators: list[Any],
    drop_prerelease: bool,
) -> tuple[Any, bool, Any, bool] | None:
    """Return the interval of versions that one branch of a range covers.

    A branch is the part of a range between two `||`, such as
    `>=1.0.0 <2.0.0`. Its first comparator is the lower bound and its last
    comparator the upper bound. Returns `(lo, lo_inc, hi, hi_inc)`, where
    the `_inc` flags say whether a bound is included and `hi` is `None`
    for a branch that is unbounded above. Returns `None` for a branch that
    starts with (<) or (<=), which we do not handle.
    """
    first, last = comparators[0], comparators[-1]
    if first.operator.startswith("<"):
        return None

    # A strict (>) lower bound excludes its version: `>1.0.0` does not
    # contain 1.0.0 itself.
    lo, lo_inc = first.semver, first.operator != ">"
    if last.operator.startswith(">"):
        # A branch ending in (>) or (>=) is unbounded above.
        hi, hi_inc = None, False
    else:
        # An upper bound is exclusive for (<), and inclusive for the (<=)
        # end of a hyphen range and for a single version.
        hi, hi_inc = last.semver, last.operator != "<"

    if drop_prerelease and lo.prerelease:
        # Raise the lower bound to its release, which the branch contains
        # even when the bound was strict: `>4.7.0-beta.0` contains 4.7.0.
        # Build a new SemVer, since `inc` changes it in place.
        lo, lo_inc = SemVer(lo.version, True).inc("patch"), True  # type: ignore[no-untyped-call]
        if hi is not None and (gt(lo, hi, True) if hi_inc else gte(lo, hi, True)):  # type: ignore[no-untyped-call]
            # The release is past the upper bound, as in
            # `4.0.0-alpha.0 - 4.0.0-rc.0`. The branch then stands for the
            # release alone.
            hi, hi_inc = lo, True

    return lo, lo_inc, hi, hi_inc


def compare_ranges(  # noqa: C901, PLR0912
    spec1: str,
    spec2: str,
    drop_prerelease1: bool = False,
    drop_prerelease2: bool = False,
) -> int | None:
    """Test whether two version specs overlap.

    Returns `None` if we cannot determine compatibility,
    otherwise return 0 if there is an overlap, 1 if
    spec1 is lower/older than spec2, and -1 if spec1
    is higher/newer than spec2.
    """
    # Test for overlapping semver ranges.
    try:
        r1 = Range(spec1, True)  # type: ignore[no-untyped-call]
        r2 = Range(spec2, True)  # type: ignore[no-untyped-call]
    except ValueError:
        return None

    # If either range is empty, we cannot verify.
    if not r1.range or not r2.range:
        return None

    # Set return_value to a sentinel value
    return_value: int | bool | None = False

    # r1.set may be a list of ranges if the range involved an ||,
    # so we need to test for overlaps between each pair.
    for r1set, r2set in itertools.product(r1.set, r2.set):
        x = _branch_interval(r1set, drop_prerelease1)
        y = _branch_interval(r2set, drop_prerelease2)

        # We do not handle (<) specifiers.
        if x is None or y is None:
            continue

        x1, x1_inc, x2, x2_inc = x
        y1, y1_inc, y2, y2_inc = y

        # Lower bound of the intersection.
        if gt(x1, y1, True):  # type: ignore[no-untyped-call]
            lo, lo_inc = x1, x1_inc
        elif gt(y1, x1, True):  # type: ignore[no-untyped-call]
            lo, lo_inc = y1, y1_inc
        else:
            lo, lo_inc = x1, x1_inc and y1_inc

        # Upper bound of the intersection.
        if x2 is None:
            hi, hi_inc = y2, y2_inc
        elif y2 is None or lt(x2, y2, True):  # type: ignore[no-untyped-call]
            hi, hi_inc = x2, x2_inc
        elif lt(y2, x2, True):  # type: ignore[no-untyped-call]
            hi, hi_inc = y2, y2_inc
        else:
            hi, hi_inc = x2, x2_inc and y2_inc

        # The ranges overlap when the intersection is non-empty: either it
        # spans versions, or it is a single version included in both.
        if (
            hi is None
            or gt(hi, lo, True)  # type: ignore[no-untyped-call]
            or (lo_inc and hi_inc and gte(hi, lo, True))  # type: ignore[no-untyped-call]
        ):
            # if we ever find an overlap, we can return immediately
            return 0

        # spec1 is lower when its upper end is at or below spec2's lower
        # end (the shared point, if any, is excluded from at least one
        # side, since a shared included point would be an overlap).
        if x2 is not None and lte(x2, y1, True):  # type: ignore[no-untyped-call]
            if return_value is False:
                # We can possibly return 1
                return_value = 1
            elif return_value == -1:
                # conflicting information, so we must return None
                return_value = None
            continue

        if y2 is not None and lte(y2, x1, True):  # type: ignore[no-untyped-call]
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
