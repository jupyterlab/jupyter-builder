# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import pytest

from jupyter_builder.federated_extensions import (
    _module_federation_flag,
    _normalize_module_federation_version,
)


@pytest.mark.parametrize("value", [None, ""])
def test_normalize_module_federation_version_unset(value):
    assert _normalize_module_federation_version(value) is None


@pytest.mark.parametrize(("value", "expected"), [(1, "1"), (2, "2"), ("1", "1"), ("2", "2")])
def test_normalize_module_federation_version_valid(value, expected):
    assert _normalize_module_federation_version(value) == expected


@pytest.mark.parametrize("value", [0, 3, "1.5", "v2", True])
def test_normalize_module_federation_version_invalid(value):
    with pytest.raises(ValueError, match="expected 1 or 2"):
        _normalize_module_federation_version(value)


def test_module_federation_flag_unset_leaves_choice_to_builder():
    assert _module_federation_flag(None, "@jupyterlab/builder") == []
    assert _module_federation_flag(None, "@jupyter/builder") == []


def test_module_federation_flag_passed_to_jupyter_builder():
    assert _module_federation_flag("2", "@jupyter/builder") == [
        "--module-federation-version",
        "2",
    ]


def test_module_federation_flag_refused_for_legacy_builder():
    with pytest.raises(ValueError, match="only supported by @jupyter/builder"):
        _module_federation_flag("1", "@jupyterlab/builder")
