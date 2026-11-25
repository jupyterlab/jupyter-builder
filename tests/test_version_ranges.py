# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from jupyter_builder.version_ranges import compare_ranges, ranges_overlap


def test_ranges_overlap_handles_invalid_semver_range():
    assert ranges_overlap("^1.0.0", "file:../builder") is None
    assert ranges_overlap("file:../builder", "^1.0.0") is None
    assert ranges_overlap("invalid-version", "another-invalid") is None


def testranges_overlap():
    assert ranges_overlap("^0.6.0", "^0.6.1")
    assert ranges_overlap(">0.1", "0.6")
    assert ranges_overlap("~0.5.0", "~0.5.2")
    assert ranges_overlap("0.5.2", "^0.5.0")

    assert not ranges_overlap("^0.5.0", "^0.6.0")
    assert not ranges_overlap("~1.5.0", "^1.6.0")

    assert ranges_overlap("*", "0.6") is None
    assert ranges_overlap("<0.6", "0.1") is None

    assert ranges_overlap("^1 || ^2", "^1")
    assert ranges_overlap("^1 || ^2", "^2")
    assert ranges_overlap("^1", "^1 || ^2")
    assert ranges_overlap("^2", "^1 || ^2")
    assert ranges_overlap("^1 || ^2", "^2 || ^3")
    assert not ranges_overlap("^1 || ^2", "^3 || ^4")
    assert not ranges_overlap("^2", "^1 || ^3")


def test_ranges_overlap_inclusive_upper_bound():
    # The upper bound of a hyphen range is inclusive.
    assert ranges_overlap("~4.2.0", "4.0.0 - 4.2.0")
    assert ranges_overlap("^4.2.0", "4.0.0 - 4.2.0")
    assert ranges_overlap("1.0.0 - 1.5.0", "1.5.0")
    assert ranges_overlap("1.5.0", "1.0.0 - 1.5.0")
    assert not ranges_overlap("4.0.0 - 4.2.0", "^4.3.0")

    # The upper bound of a caret or tilde range is exclusive.
    assert not ranges_overlap("1.5.0", "~1.4.0")
    assert not ranges_overlap("2.0.0", "^1.4.0")
    assert not ranges_overlap("~1.4.0", "1.5.0")


def test_ranges_overlap_strict_lower_bound():
    # A strict (>) lower bound excludes its version.
    assert not ranges_overlap(">1.0.0", "1.0.0")
    assert not ranges_overlap("1.0.0", ">1.0.0")
    assert not ranges_overlap(">2.0.0", "1.0.0 - 2.0.0")
    assert not ranges_overlap("1.0.0 - 2.0.0", ">2.0.0")
    assert not ranges_overlap(">1.0.0 <2.0.0", "1.0.0")
    assert not ranges_overlap("1.0.0", ">1.0.0 <2.0.0")

    assert ranges_overlap(">1.0.0", "1.0.1")
    assert ranges_overlap(">1.0.0", ">1.0.0")
    assert ranges_overlap(">1.0.0", ">2.0.0")
    assert ranges_overlap(">1.0.0", ">=1.0.0")
    assert ranges_overlap(">1.0.0 <2.0.0", ">1.0.0 <2.0.0")


def test_ranges_overlap_strict_lower_bound_drop_prerelease():
    # Once its prerelease is dropped, a strict (>) lower bound includes the release.
    assert ranges_overlap(">4.7.0-beta.0", "4.7.0", drop_prerelease1=True)
    assert ranges_overlap("4.7.0", ">4.7.0-beta.0", drop_prerelease2=True)
    assert ranges_overlap(">4.7.0-beta.0 <5.0.0", "4.7.0", drop_prerelease1=True)
    # The same branch is compared again for each branch of the other spec.
    assert ranges_overlap(">4.7.0-beta.0", "^3.0.0 || 4.7.0", drop_prerelease1=True)


def testcompare_ranges():
    assert compare_ranges("^1 || ^2", "^1") == 0
    assert compare_ranges("^1 || ^2", "^2 || ^3") == 0
    assert compare_ranges("^1 || ^2", "^3 || ^4") == 1
    assert compare_ranges("^3 || ^4", "^1 || ^2") == -1
    assert compare_ranges("^2 || ^3", "^1 || ^4") is None


def test_compare_ranges_strict_lower_bound():
    assert compare_ranges(">1.0.0", "1.0.0") == -1
    assert compare_ranges("1.0.0", ">1.0.0") == 1
    assert compare_ranges(">2.0.0", "1.0.0 - 2.0.0") == -1


def test_compare_ranges_drop_prerelease_past_upper_bound():
    # Dropping the prerelease can push a branch's lower bound past its upper
    # bound. The branch then stands for the release version alone.
    assert compare_ranges("4.0.0-alpha.0 - 4.0.0-rc.0", ">=3.0.0", drop_prerelease1=True) == 0
    assert compare_ranges(">=4.7.0-alpha.0 <4.7.0", "~4.7.0-beta.2", drop_prerelease1=True) == 0
    assert compare_ranges(">=3.0.0", "4.0.0-alpha.0 - 4.0.0-rc.0", drop_prerelease2=True) == 0
    assert compare_ranges("4.0.0-alpha.0 - 4.0.0-rc.0", "^4.1.0", drop_prerelease1=True) == 1
    assert compare_ranges("4.0.0-alpha.0 - 4.0.0-rc.0", "^3.0.0", drop_prerelease1=True) == -1
