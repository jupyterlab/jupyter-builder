# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Test the content provider that adds vendored code to the wheel's PEP 770 SBOM."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pytest
from python_sbom import SbomError

from sbom_content import dist_info, npm_component, yarn_components, yarn_version

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = REPO_ROOT / "THIRD_PARTY_LICENSES/yarn.js.third-party-licenses.json"


def test_scoped_package_purl_and_license():
    component = npm_component(
        {"name": "@yarnpkg/cli", "versionInfo": "3.5.0", "licenseId": "BSD-2-Clause"},
    )
    assert component["purl"] == "pkg:npm/%40yarnpkg/cli@3.5.0"
    assert component["bom-ref"] == component["purl"]
    assert component["name"] == "@yarnpkg/cli"
    assert component["licenses"] == [
        {"license": {"id": "BSD-2-Clause", "acknowledgement": "declared"}},
    ]


def test_unscoped_package_purl():
    component = npm_component({"name": "semver", "versionInfo": "7.3.8", "licenseId": "ISC"})
    assert component["purl"] == "pkg:npm/semver@7.3.8"


def test_one_component_per_package_in_report():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    bundle, dependency = yarn_components(report, yarn_version(REPO_ROOT / "package.json"), "0" * 64)
    children = bundle["components"]
    assert len(children) == len(report["packages"])
    refs = [child["bom-ref"] for child in children]
    assert len(set(refs)) == len(refs)
    assert dependency == {"ref": bundle["bom-ref"], "dependsOn": refs}
    assert [child["licenses"][0]["license"]["id"] for child in children] == [
        package["licenseId"] for package in report["packages"]
    ]


def test_yarn_version_must_match_report():
    cli = {"name": "@yarnpkg/cli", "versionInfo": "3.5.0", "licenseId": "MIT"}
    with pytest.raises(SbomError, match="@yarnpkg/cli"):
        yarn_components({"packages": [cli]}, "4.0.0", "0" * 64)  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("manager", "version"),
    [("yarn@3.5.0", "3.5.0"), ("yarn@3.5.0+sha224.abc", "3.5.0")],
)
def test_yarn_version(tmp_path, manager, version):
    package_json = tmp_path / "package.json"
    package_json.write_text(json.dumps({"packageManager": manager}), encoding="utf-8")
    assert yarn_version(package_json) == version


def test_dist_info():
    version_py = b"__version__ = VERSION = '1.3.1'\n"
    assert dist_info(version_py) == PurePosixPath("jupyter_builder-1.3.1.dist-info")


@pytest.mark.slow
def test_wheel_has_sbom(tmp_path):
    pytest.importorskip("build")
    # Builds the sdist, then the wheel from it, so the sdist must carry the provider.
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(tmp_path), str(REPO_ROOT)],
        cwd=tmp_path,
        check=True,
    )
    (wheel,) = tmp_path.glob("*.whl")
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        (sbom_name,) = [n for n in names if n.endswith(".dist-info/sboms/jupyter-builder.cdx.json")]
        sbom = json.loads(zf.read(sbom_name))
    assert "sbom_content.py" not in names
    (yarn,) = [c for c in sbom["components"] if c["name"] == "yarn"]
    purl = f"pkg:npm/%40yarnpkg/cli@{yarn['version']}"
    assert purl in {c["purl"] for c in yarn["components"]}
