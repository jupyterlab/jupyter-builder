# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from subprocess import Popen, run

import pytest


def helper(dest):
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
            dest,
        ],
        cwd=dest,
        check=True,
    )
    log = Path(dest) / "yarn.lock"
    log.touch()


# ---------------------- BUILD TESTS --------------------------------------
def test_files_build(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(
        ["jlpm", "install"],
        cwd=extension_folder,
        check=True,
        env=env,
    )

    run(["jlpm", "run", "build:lib:prod"], cwd=extension_folder, check=True)

    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"

    expected_files = ["static/style.js", "package.json"]

    for filename in expected_files:
        filepath = folder_path / filename
        assert filepath.exists(), f"File {filename} does not exist in {folder_path}!"


def test_files_build_development(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(
        ["jlpm", "install"],
        cwd=extension_folder,
        check=True,
        env=env,
    )

    run(["jlpm", "run", "build:lib:prod"], cwd=extension_folder, check=True)

    run(
        ["jupyter-builder", "build", "--development", "true", str(extension_folder)],
        cwd=extension_folder,
        check=True,
    )

    folder_path = extension_folder / "myextension/labextension"

    expected_files = ["static/style.js", "package.json", "build_log.json"]

    for filename in expected_files:
        filepath = folder_path / filename
        assert filepath.exists(), f"File {filename} does not exist in {folder_path}!"


def test_files_build_jupyterlab_builder(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    # The template declares @jupyter/builder by default, which is the preferred
    # builder marker. To exercise the @jupyterlab/builder path we swap it in for
    # @jupyter/builder before installing.
    prepare = (
        "const fs=require('fs');"
        " const p=require('./package.json');"
        " p.resolutions = p.resolutions || {};"
        " p.resolutions.webpack='5.106.0';"
        " p.devDependencies = p.devDependencies || {};"
        " delete p.devDependencies['@jupyter/builder'];"
        " p.devDependencies['@jupyterlab/builder'] = '^4.0.0';"
        " fs.writeFileSync('package.json', JSON.stringify(p,null,2));"
    )
    run(["node", "-e", prepare], cwd=extension_folder, check=True)
    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(["jlpm", "install"], cwd=extension_folder, check=True, env=env)
    run(["jlpm", "run", "build:lib:prod"], cwd=extension_folder, check=True)

    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"
    expected_files = ["static/style.js", "package.json"]
    for filename in expected_files:
        filepath = folder_path / filename
        assert filepath.exists(), f"File {filename} does not exist in {folder_path}!"


# --------------------------------- WATCH TESTS ---------------------------------------


def list_files_in_static(directory):
    """List all filenames in the specified directory."""
    return {f.name for f in Path(directory).glob("*")}


def test_watch_functionality(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(
        ["jlpm", "install"],
        cwd=extension_folder,
        check=True,
        env=env,
    )

    run(["jlpm", "run", "build:lib:prod"], cwd=extension_folder, check=True)

    # Path to the TypeScript file to change
    index_ts_path = extension_folder / "src/index.ts"

    static_dir = extension_folder / "myextension/labextension/static"

    # Ensure the TypeScript file exists
    assert index_ts_path.exists(), f"File {index_ts_path} does not exist!"

    # List filenames in static directory before change
    initial_files = list_files_in_static(static_dir)

    is_windows = platform.system() == "Windows"
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if is_windows else {}

    watch_process = Popen(
        ["jupyter-builder", "watch", str(extension_folder)],
        cwd=extension_folder,
        **kwargs,
    )

    # This sleep time makes sure that the comment is added only after the watch process is running.
    time.sleep(100)

    try:
        # Add a comment to the TypeScript file to trigger watch
        with index_ts_path.open("a") as f:
            f.write("// Test comment to trigger watch\n")

        # Wait for watch process to detect change and rebuild
        time.sleep(100)  # Adjust this time if needed

        # List filenames in static directory after change
        final_files = list_files_in_static(static_dir)

        # Compare the initial and final file lists
        assert initial_files != final_files, (
            " No changes detected in the static directory."
            "Watch process may not have triggered correctly!"
        )

    finally:
        watch_process.terminate()
        # Give some time to terminate the process cleanly
        time.sleep(5)
        if watch_process.poll() is None:
            watch_process.kill()


def test_watch_functionality_jupyterlab_builder(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    # The template declares @jupyter/builder by default, which is the preferred
    # builder marker. To exercise the @jupyterlab/builder path we swap it in for
    # @jupyter/builder before installing.
    prepare = (
        "const fs=require('fs');"
        " const p=require('./package.json');"
        " p.resolutions = p.resolutions || {};"
        " p.resolutions.webpack='5.106.0';"
        " p.devDependencies = p.devDependencies || {};"
        " delete p.devDependencies['@jupyter/builder'];"
        " p.devDependencies['@jupyterlab/builder'] = '^4.0.0';"
        " fs.writeFileSync('package.json', JSON.stringify(p,null,2));"
    )
    run(["node", "-e", prepare], cwd=extension_folder, check=True)
    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(["jlpm", "install"], cwd=extension_folder, check=True, env=env)
    run(["jlpm", "run", "build:lib:prod"], cwd=extension_folder, check=True)

    index_ts_path = extension_folder / "src/index.ts"
    static_dir = extension_folder / "myextension/labextension/static"
    assert index_ts_path.exists(), f"File {index_ts_path} does not exist!"

    initial_files = list_files_in_static(static_dir)

    is_windows = platform.system() == "Windows"
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if is_windows else {}

    watch_process = Popen(
        ["jupyter-builder", "watch", str(extension_folder)],
        cwd=extension_folder,
        **kwargs,
    )

    time.sleep(100)

    try:
        with index_ts_path.open("a") as f:
            f.write("// Test comment to trigger watch\n")

        time.sleep(100)

        final_files = list_files_in_static(static_dir)
        assert initial_files != final_files, (
            "No changes detected in the static directory."
            " Watch process may not have triggered correctly!"
        )
    finally:
        watch_process.terminate()
        time.sleep(5)
        if watch_process.poll() is None:
            watch_process.kill()


def _seed_core_meta_cache(version, builder_range):
    """Seed the core-meta cache so ``get_core_meta`` resolves offline."""
    home = os.environ.get("HOME") or str(Path.home())
    cache_file = (
        Path(home) / ".cache" / "jupyterlab_builder" / "core" / version / "core.package.json"
    )
    if cache_file.exists():
        return
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "name": "@jupyterlab/application-top",
                "version": "4.5.9",
                "devDependencies": {"@jupyterlab/builder": builder_range},
            },
            indent=2,
        ),
    )


def test_builder_version_mismatch(tmp_path):
    extension_folder = tmp_path / "ext"
    extension_folder.mkdir()
    helper(str(extension_folder))

    # Seed the core-meta cache for 4.5.x so the build resolves offline instead
    # of downloading from GitHub (which is rate-limited and flaky). The
    # dummy declares an incompatible @jupyterlab/builder range to trigger the
    # version mismatch error this test asserts on.
    _seed_core_meta_cache("4.5.x", "^4.5.9")

    package_json_path = extension_folder / "package.json"

    # The template ships `@jupyter/builder` by default, but the version
    # incompatibility check can only be verified on `@jupyterlab/builder` for
    # now. So we remove `@jupyter/builder` and pin `@jupyterlab/builder` to an
    # incompatible range, leaving it as the only builder marker. We keep the
    # test this way for now; it will be changed later.
    package_data = json.loads(package_json_path.read_text())
    package_data["devDependencies"].pop("@jupyter/builder", None)
    package_data["devDependencies"]["@jupyterlab/builder"] = "4.0.0"
    package_json_path.write_text(json.dumps(package_data, indent=2))

    env = os.environ.copy()
    env.update({"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"})
    run(
        ["jlpm", "install"],
        cwd=extension_folder,
        check=True,
        env=env,
    )

    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        run(
            ["jupyter-builder", "build", str(extension_folder), "--core-version", "4.5.x"],
            cwd=extension_folder,
            check=True,
            capture_output=True,
            text=True,
        )
    # Check if the expected error message is in the output
    assert re.search(
        (
            r"ValueError: Extensions require a devDependency on @jupyterlab/builder@\^.+?, "
            r"you have a dependency on 4\.0\.0"
        ),
        excinfo.value.stderr,
    ), "Expected version mismatch error message not found in output!"
