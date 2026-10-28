# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator


@pytest.fixture
def metadata_schema():
    schema_path = Path(__file__).resolve().parent.parent / "src" / "metadata_schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_metadata_schema_is_valid_draft7(metadata_schema):
    """The metadata schema itself must be a valid JSON Schema Draft-07 document."""
    Draft7Validator.check_schema(metadata_schema)


@pytest.mark.parametrize(
    "invalid_shared_packages",
    [
        "not-an-object",
        123,
        True,
        ["package-a"],
    ],
)
def test_shared_packages_rejects_non_object(metadata_schema, invalid_shared_packages):
    """SharedPackages must be an object, not a string, number, boolean, or array."""
    validator = Draft7Validator(metadata_schema)
    errors = list(validator.iter_errors({"sharedPackages": invalid_shared_packages}))
    assert len(errors) > 0
    assert any("sharedPackages" in list(error.path) for error in errors)


@pytest.mark.parametrize(
    "invalid_config",
    [
        # Package config must be false or an object matching sharedConfig
        123,
        "true",
        {"unknownOption": 123},
        {"bundled": "not-a-boolean"},
        {"singleton": "not-a-boolean"},
        {"strictVersion": "not-a-boolean"},
        {"requiredVersion": 123},
    ],
)
def test_shared_packages_rejects_invalid_package_config(metadata_schema, invalid_config):
    """Package definitions inside sharedPackages must adhere to sharedConfig schema."""
    validator = Draft7Validator(metadata_schema)
    errors = list(validator.iter_errors({"sharedPackages": {"test-package": invalid_config}}))
    assert len(errors) > 0


@pytest.mark.parametrize(
    "valid_shared_packages",
    [
        {},
        {"my-pkg": False},
        {"my-pkg": {}},
        {"my-pkg": {"bundled": True}},
        {"my-pkg": {"singleton": True}},
        {"my-pkg": {"requiredVersion": "^1.2.0"}},
        {"my-pkg": {"requiredVersion": False}},
        {"my-pkg": {"strictVersion": True}},
        {
            "pkg-a": False,
            "pkg-b": {
                "bundled": False,
                "singleton": True,
                "requiredVersion": ">=2.0.0",
                "strictVersion": True,
            },
        },
    ],
)
def test_shared_packages_accepts_valid_config(metadata_schema, valid_shared_packages):
    """Valid sharedPackages definitions must pass schema validation."""
    validator = Draft7Validator(metadata_schema)
    errors = list(validator.iter_errors({"sharedPackages": valid_shared_packages}))
    assert errors == []


def test_shared_config_boolean_defaults(metadata_schema):
    """Boolean fields in sharedConfig must have boolean defaults, not strings."""
    shared_config = metadata_schema["definitions"]["sharedConfig"]["properties"]
    assert shared_config["bundled"]["default"] is True
    assert shared_config["singleton"]["default"] is False
