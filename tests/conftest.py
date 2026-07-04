# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
import os
import shutil
from pathlib import Path
from subprocess import run

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Subprocess coverage (`[tool.coverage.run] patch = ["subprocess"]`) makes the
# `jupyter-builder`/`jlpm` CLIs spawned by the tests record their own coverage
# data. Point every process at an absolute data file in the repo root so
# pytest-cov finds and combines all of the pieces.
os.environ.setdefault("COVERAGE_FILE", str(REPO_ROOT / ".coverage"))

# The template declares @jupyter/builder by default. To exercise the @jupyterlab/builder
#  path we swap it in before installing.
_SWAP_TO_JUPYTERLAB_BUILDER = (
    "const fs=require('fs');"
    " const p=require('./package.json');"
    " p.resolutions = p.resolutions || {};"
    " p.resolutions.webpack='5.106.0';"
    " p.devDependencies = p.devDependencies || {};"
    " delete p.devDependencies['@jupyter/builder'];"
    " p.devDependencies['@jupyterlab/builder'] = '^4.0.0';"
    " fs.writeFileSync('package.json', JSON.stringify(p,null,2));"
)


def _copy_extension(source, dest):
    shutil.copytree(source, dest, symlinks=True)
    return dest


def _jlpm_install(folder):
    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(["jlpm", "install"], cwd=folder, check=True, env=env)


@pytest.fixture(scope="session")
def template_skeleton(tmp_path_factory):
    """Render the extension template once per session (clones over the network)."""
    dest = tmp_path_factory.mktemp("template") / "ext"
    dest.mkdir()
    run(
        [
            "copier",
            "copy",
            "--trust",
            "-l",
            "-d",
            "author_name=tester",
            "-d",
            "repository=dummy",
            "https://github.com/jupyterlab/extension-template",
            str(dest),
        ],
        cwd=dest,
        check=True,
    )
    (dest / "yarn.lock").touch()
    return dest


@pytest.fixture(scope="session")
def built_extension(template_skeleton, tmp_path_factory):
    """Install and build the templated extension once for the whole session."""
    dest = _copy_extension(template_skeleton, tmp_path_factory.mktemp("built") / "ext")
    _jlpm_install(dest)
    run(["jlpm", "run", "build:lib:prod"], cwd=dest, check=True)
    return dest


@pytest.fixture(scope="session")
def built_jupyterlab_builder_extension(template_skeleton, tmp_path_factory):
    """Install and build the extension with @jupyterlab/builder swapped in."""
    dest = _copy_extension(template_skeleton, tmp_path_factory.mktemp("built_jlb") / "ext")
    run(["node", "-e", _SWAP_TO_JUPYTERLAB_BUILDER], cwd=dest, check=True)
    _jlpm_install(dest)
    run(["jlpm", "run", "build:lib:prod"], cwd=dest, check=True)
    return dest


@pytest.fixture(scope="session")
def installed_mismatch_extension(template_skeleton, tmp_path_factory):
    """Install the extension pinned to an incompatible @jupyterlab/builder.

    The version incompatibility check can only be verified on
    @jupyterlab/builder for now, so @jupyter/builder is removed and
    @jupyterlab/builder pinned to an incompatible version, leaving it as the
    only builder marker.
    """
    dest = _copy_extension(template_skeleton, tmp_path_factory.mktemp("mismatch") / "ext")
    package_json_path = dest / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data["devDependencies"].pop("@jupyter/builder", None)
    package_data["devDependencies"]["@jupyterlab/builder"] = "4.0.0"
    package_json_path.write_text(json.dumps(package_data, indent=2))
    _jlpm_install(dest)
    return dest


@pytest.fixture
def extension_folder(built_extension, tmp_path):
    """Give the test its own isolated copy of the pre-built extension."""
    return _copy_extension(built_extension, tmp_path / "ext")


@pytest.fixture
def jupyterlab_builder_extension_folder(built_jupyterlab_builder_extension, tmp_path):
    """Give the test its own isolated copy of the @jupyterlab/builder variant."""
    return _copy_extension(built_jupyterlab_builder_extension, tmp_path / "ext")


@pytest.fixture
def mismatch_extension_folder(installed_mismatch_extension, tmp_path):
    """Give the test its own isolated copy of the version-mismatch variant."""
    return _copy_extension(installed_mismatch_extension, tmp_path / "ext")
