# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import platform
import signal
import subprocess
import time
from subprocess import run, Popen
from pathlib import Path


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
    run(["jlpm", "run", "build:prod"], cwd=extension_folder, check=True)

    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"

    expected_files = ["static/style.js", "package.json"]

    for filename in expected_files:
        filepath = os.path.join(folder_path, filename)
        assert os.path.exists(filepath), f"File {filename} does not exist in {folder_path}!"


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
    run(["jlpm", "run", "build:prod"], cwd=extension_folder, check=True)

    run(
        ["jupyter-builder", "build", "--development", "true", str(extension_folder)],
        cwd=extension_folder,
        check=True,
    )

    folder_path = extension_folder / "myextension/labextension"

    expected_files = ["static/style.js", "package.json", "build_log.json"]

    for filename in expected_files:
        filepath = os.path.join(folder_path, filename)
        assert os.path.exists(filepath), f"File {filename} does not exist in {folder_path}!"


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
    run(["jlpm", "run", "build"], cwd=extension_folder, check=True)

    # Path to the TypeScript file to change
    index_ts_path = extension_folder / "src/index.ts"

    static_dir = extension_folder / "myextension/labextension/static"

    # Ensure the TypeScript file exists
    assert index_ts_path.exists(), f"File {index_ts_path} does not exist!"

    # List filenames in static directory before change
    initial_files = list_files_in_static(static_dir)

    is_windows = platform.system() == "Windows"
    if is_windows:
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        kwargs = {}

    watch_process = Popen(
        ["jupyter-builder", "watch", str(extension_folder)], cwd=extension_folder, **kwargs
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

    # Note: The ideal process of termination is given below, but does not work
    #     if is_windows:
    #         watch_process.send_signal(signal.CTRL_C_EVENT)

    #     else:
    #         watch_process.send_signal(signal.SIGINT)
    #     watch_process.wait()
