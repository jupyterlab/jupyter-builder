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


def _use_local_builder(folder, tarball):
    """Point the extension at the @jupyter/builder built from this checkout."""
    package_json_path = folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    resolutions = package_data.setdefault("resolutions", {})
    # `as_posix` because a yarn descriptor may not contain Windows separators.
    resolutions["@jupyter/builder"] = f"file:{tarball.as_posix()}"
    package_json_path.write_text(json.dumps(package_data, indent=2))


def _assert_local_builder_installed(folder):
    """Fail if the `resolutions` swap quietly fell back to the released builder.

    Comparing versions would not detect the fallback: until the next release is
    cut, the working tree and the package on npm report the same version, so a
    resolution that stops taking effect would leave the whole suite validating
    the last release with no visible symptom.
    """
    installed = folder / "node_modules/@jupyter/builder/lib/extensionConfig.js"
    local = REPO_ROOT / "lib/extensionConfig.js"
    assert installed.exists(), f"{installed} is missing; @jupyter/builder was not installed."
    assert installed.read_bytes() == local.read_bytes(), (
        f"{installed} differs from {local}: the `resolutions` entry did not take effect, "
        "so these tests would exercise the last release instead of this checkout."
    )


@pytest.fixture(scope="session")
def local_builder_tarball(tmp_path_factory):
    """Pack the @jupyter/builder in this checkout as an installable tarball.

    The extension template depends on @jupyter/builder from npm, so without
    swapping in a locally built tarball the end-to-end tests would only ever
    exercise the last release rather than the code under test.
    """
    dest = tmp_path_factory.mktemp("builder-pack") / "jupyter-builder.tgz"
    run(["jlpm", "install", "--immutable"], cwd=REPO_ROOT, check=True)
    run(["jlpm", "run", "build:lib:prod"], cwd=REPO_ROOT, check=True)
    # `jlpm pack` rather than `npm pack`: npm ships as a `.cmd` shim on Windows,
    # which `subprocess` cannot launch without a shell.
    run(["jlpm", "pack", "--out", str(dest)], cwd=REPO_ROOT, check=True)
    return dest


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
            # Renders a `schema/` directory and sets `jupyterlab.schemaDir`, so
            # the builds below cover schema handling too.
            "-d",
            "has_settings=true",
            "https://github.com/jupyterlab/extension-template",
            str(dest),
        ],
        cwd=dest,
        check=True,
    )
    (dest / "yarn.lock").touch()
    return dest


@pytest.fixture(scope="session")
def built_extension(template_skeleton, local_builder_tarball, tmp_path_factory):
    """Install and build the templated extension once for the whole session."""
    dest = _copy_extension(template_skeleton, tmp_path_factory.mktemp("built") / "ext")
    _use_local_builder(dest, local_builder_tarball)
    _jlpm_install(dest)
    _assert_local_builder_installed(dest)
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
def glob_hostile_extension_folder(built_extension, tmp_path):
    """Give the test a copy of the extension under a directory name containing glob syntax.

    `[` and `{` are the characters that actually change what a glob pattern
    means -- verified against the glob release this package depends on, where a
    directory named `br[ack]ets` makes the pre-fix `path.join`-built pattern
    match nothing. Building here therefore reproduces the issue on every
    platform, not only on Windows, where the trigger was the path separator.
    """
    return _copy_extension(built_extension, tmp_path / "ext[1]{a,b}")


@pytest.fixture
def jupyterlab_builder_extension_folder(built_jupyterlab_builder_extension, tmp_path):
    """Give the test its own isolated copy of the @jupyterlab/builder variant."""
    return _copy_extension(built_jupyterlab_builder_extension, tmp_path / "ext")


@pytest.fixture
def mismatch_extension_folder(installed_mismatch_extension, tmp_path):
    """Give the test its own isolated copy of the version-mismatch variant."""
    return _copy_extension(installed_mismatch_extension, tmp_path / "ext")
