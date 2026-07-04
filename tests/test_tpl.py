# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import platform
import re
import subprocess
import time
from pathlib import Path
from subprocess import Popen, run

import pytest

pytestmark = pytest.mark.slow

# Ceilings for the watch tests; polling returns as soon as the condition holds.
WATCH_INITIAL_BUILD_TIMEOUT = 300
WATCH_REBUILD_TIMEOUT = 180


def wait_for(condition, timeout, interval=2):
    """Poll `condition` until it is truthy or `timeout` seconds have elapsed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return bool(condition())


# ---------------------- BUILD TESTS --------------------------------------
def test_files_build(extension_folder):
    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"

    expected_files = ["static/style.js", "package.json"]

    for filename in expected_files:
        filepath = folder_path / filename
        assert filepath.exists(), f"File {filename} does not exist in {folder_path}!"


def test_files_build_development(extension_folder):
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


def test_files_build_jupyterlab_builder(jupyterlab_builder_extension_folder):
    extension_folder = jupyterlab_builder_extension_folder
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


def assert_watch_rebuilds(extension_folder):
    """Start `jupyter-builder watch` and check that a source change rebuilds."""
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

    try:
        # Wait until the watch process is running and its initial build has
        # landed in the static directory, so that the comment below is only
        # added after watching has started.
        wait_for(
            lambda: (
                watch_process.poll() is not None
                or list_files_in_static(static_dir) != initial_files
            ),
            timeout=WATCH_INITIAL_BUILD_TIMEOUT,
        )
        assert watch_process.poll() is None, "Watch process exited before the initial build!"
        files_after_initial_build = list_files_in_static(static_dir)

        # Add a comment to the TypeScript file to trigger watch
        with index_ts_path.open("a") as f:
            f.write("// Test comment to trigger watch\n")

        # Wait for the watch process to detect the change and rebuild. On
        # timeout, fall through: the assertion below decides the outcome.
        wait_for(
            lambda: list_files_in_static(static_dir) != files_after_initial_build,
            timeout=WATCH_REBUILD_TIMEOUT,
        )

        # List filenames in static directory after change
        final_files = list_files_in_static(static_dir)

        # Compare the initial and final file lists
        assert initial_files != final_files, (
            " No changes detected in the static directory."
            "Watch process may not have triggered correctly!"
        )

    finally:
        watch_process.terminate()
        try:
            watch_process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            watch_process.kill()
            watch_process.wait()


def test_watch_functionality(extension_folder):
    assert_watch_rebuilds(extension_folder)


def test_watch_functionality_jupyterlab_builder(jupyterlab_builder_extension_folder):
    assert_watch_rebuilds(jupyterlab_builder_extension_folder)


def test_builder_version_mismatch(mismatch_extension_folder):
    extension_folder = mismatch_extension_folder
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        run(
            ["jupyter-builder", "build", str(extension_folder), "--core-version", "4.5.x"],
            cwd=extension_folder,
            check=True,
            capture_output=True,
            text=True,
        )
    # Check if the expected error message is in the output
    output = excinfo.value.stderr
    assert re.search(
        (
            r"ValueError: Extensions require a devDependency on @jupyterlab/builder@\^[^,]+, "
            r"you have a dependency on 4\.0\.0"
        ),
        output,
    ), "Expected version mismatch error message not found in output!"
