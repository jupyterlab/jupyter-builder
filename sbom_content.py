# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Add the code vendored into jupyter_builder to the PEP 770 SBOM of its wheel.

python-sbom describes a wheel from its core metadata, so it cannot see the JavaScript
packages bundled into ``jupyter_builder/yarn.js`` or the node-semver port in
``jupyter_builder/jupyterlab_semver.py``. This content provider adds both.

It runs only while a wheel is built: ``[tool.python-sbom]`` in pyproject.toml names it,
``jupyter_builder`` never imports it, and the wheel does not ship it.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, TypedDict

from packageurl import PackageURL
from python_sbom import ContentProvider, Contributions, SbomError

if TYPE_CHECKING:
    from pathlib import Path

    from python_sbom import Component, Dependency, License, ProviderContext

YARN_JS = PurePosixPath("jupyter_builder/yarn.js")
SEMVER_PY = PurePosixPath("jupyter_builder/jupyterlab_semver.py")
# Written by hatchling's version hook, with the version the .dist-info directory is named for.
VERSION_PY = PurePosixPath("jupyter_builder/_version.py")
# Where license-files puts the report of scripts/generate_yarn_licenses.py, inside .dist-info.
YARN_REPORT = PurePosixPath("licenses/THIRD_PARTY_LICENSES/yarn.js.third-party-licenses.json")

# See THIRD_PARTY_LICENSES/semver.LICENSE.txt. The vendored file names upstream commit
# b42e989, three commits after the 0.2.0 tag. None of those three touch semver/__init__.py,
# and setup.py at that commit still says 0.2.0.
SEMVER_VERSION = "0.2.0"
SEMVER_COMMIT = "b42e9896e391e086b773fc621b23fa299d16b874"


class LicenseRecord(TypedDict):
    """One package in the yarn.js report, in the schema JSONLicenseWebpackPlugin emits."""

    name: str
    versionInfo: str
    licenseId: str


class LicenseReport(TypedDict):
    """The yarn.js report: every package esbuild bundled into the file."""

    packages: list[LicenseRecord]


def declared_licenses(license_id: str) -> list[License]:
    """Return the license a package.json declares, as an SPDX id or expression."""
    if not license_id:
        return []
    if " " in license_id:
        return [{"expression": license_id, "acknowledgement": "declared"}]
    return [{"license": {"id": license_id, "acknowledgement": "declared"}}]


def npm_component(record: LicenseRecord) -> Component:
    """Map one package in the yarn.js report to a component named by its npm purl."""
    scope, _, name = record["name"].rpartition("/")
    purl = PackageURL(
        type="npm",
        namespace=scope or None,
        name=name,
        version=record["versionInfo"],
    ).to_string()
    component: Component = {
        "type": "library",
        "bom-ref": purl,
        "name": record["name"],
        "version": record["versionInfo"],
        "purl": purl,
    }
    if licenses := declared_licenses(record["licenseId"]):
        component["licenses"] = licenses
    return component


def yarn_components(
    report: LicenseReport,
    yarn_version: str,
    sha256: str,
) -> tuple[Component, Dependency]:
    """Map the yarn.js report to a component for the bundle, with one nested per package.

    The bundle depends on each package it holds. ``yarn_version`` must be the version of
    ``@yarnpkg/cli`` in the report, so the bundle cannot name a different Yarn than the
    packages describe.
    """
    packages = report["packages"]
    cli = {p["versionInfo"] for p in packages if p["name"] == "@yarnpkg/cli"}
    if cli != {yarn_version}:
        msg = f"packageManager names yarn {yarn_version}, the yarn.js report @yarnpkg/cli {cli}"
        raise SbomError(msg)
    children = [npm_component(p) for p in packages]
    bundle: Component = {
        "type": "application",
        "bom-ref": f"vendored:{YARN_JS}",
        "name": "yarn",
        "version": yarn_version,
        "description": f"The Yarn CLI bundle, vendored as {YARN_JS}",
        "hashes": [{"alg": "SHA-256", "content": sha256}],
        "externalReferences": [{"type": "vcs", "url": "https://github.com/yarnpkg/berry"}],
        "components": children,
    }
    return bundle, {"ref": bundle["bom-ref"], "dependsOn": [c["bom-ref"] for c in children]}


def semver_component(sha256: str) -> Component:
    """Return the component for the vendored node-semver port."""
    purl = PackageURL(type="pypi", name="node-semver", version=SEMVER_VERSION).to_string()
    return {
        "type": "library",
        "bom-ref": f"vendored:{SEMVER_PY}",
        "name": "node-semver",
        "version": SEMVER_VERSION,
        "purl": purl,
        "description": f"podhmo's Python port of node-semver, vendored with changes as {SEMVER_PY}",
        "licenses": declared_licenses("MIT"),
        "hashes": [{"alg": "SHA-256", "content": sha256}],
        "externalReferences": [
            {
                "type": "vcs",
                "url": f"https://github.com/podhmo/python-node-semver/tree/{SEMVER_COMMIT}",
            },
        ],
    }


def yarn_version(package_json: Path) -> str:
    """Return the Yarn version in the ``packageManager`` field of package.json."""
    manager = json.loads(package_json.read_text(encoding="utf-8"))["packageManager"]
    # Corepack may append the archive's hash, as in yarn@3.5.0+sha224.<digest>.
    name, _, version = str(manager).partition("+")[0].partition("@")
    if name != "yarn" or not version:
        msg = f"packageManager in {package_json} is {manager!r}, not yarn@<version>"
        raise SbomError(msg)
    return version


def dist_info(version_py: bytes) -> PurePosixPath:
    """Return the wheel's .dist-info directory, named for the version in ``_version.py``."""
    for node in ast.parse(version_py).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            return PurePosixPath(f"jupyter_builder-{ast.literal_eval(node.value)}.dist-info")
    msg = f"{VERSION_PY} assigns no __version__"
    raise SbomError(msg)


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 digest of ``data`` as lowercase hex."""
    return hashlib.sha256(data).hexdigest()


class VendoredContent(ContentProvider):
    """Add yarn.js, the packages bundled into it, and the node-semver port to the SBOM."""

    def contributions(self, context: ProviderContext) -> Contributions:
        """Read the vendored files and the yarn.js report from the wheel being built."""
        report_path = dist_info(context.read(VERSION_PY)) / YARN_REPORT
        report: LicenseReport = json.loads(context.read(report_path))
        yarn, yarn_dependencies = yarn_components(
            report,
            yarn_version(context.root / "package.json"),
            sha256_hex(context.read(YARN_JS)),
        )
        semver = semver_component(sha256_hex(context.read(SEMVER_PY)))
        return Contributions(components=[yarn, semver], dependencies=[yarn_dependencies])
