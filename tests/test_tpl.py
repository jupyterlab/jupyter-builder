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


def test_build_records_remote_entry(glob_hostile_extension_folder):
    """`_build.load` must name the generated remoteEntry file.

    Regression test for https://github.com/jupyterlab/jupyter-builder/issues/163:
    the glob locating `remoteEntry.<hash>.js` is handed a native path, and on
    Windows its backslashes are consumed as glob escape characters, so nothing
    matches and `load` is written as a bare `static`, which JupyterLab then
    fails to fetch.

    Built from a directory whose name contains glob syntax so that the same
    empty match happens on POSIX too; otherwise this test could only ever fail
    on the two Windows CI legs.
    """
    extension_folder = glob_hostile_extension_folder
    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    output_dir = extension_folder / "myextension/labextension"
    build_data = json.loads((output_dir / "package.json").read_text())["jupyterlab"]["_build"]
    load = build_data["load"]

    # `load` is turned into a URL by JupyterLab, so it must be `/`-separated
    # regardless of the platform the extension was built on.
    assert re.fullmatch(r"static/remoteEntry\.[0-9a-f]+\.js", load), (
        f"Unexpected _build.load entry: {load!r}"
    )
    assert (output_dir / load).exists(), f"{load} is missing from {output_dir}!"


def test_build_copies_schemas(glob_hostile_extension_folder):
    """A declared `schemaDir` must be copied to `<outputDir>/schemas/<name>`.

    Second occurrence of the glob bug from
    https://github.com/jupyterlab/jupyter-builder/issues/163: on Windows the
    schema glob matches nothing, so the build succeeds while silently emitting
    only `package.json.orig` and the extension's settings never register.

    Built from a glob-hostile directory for the same reason as
    `test_build_records_remote_entry`.
    """
    extension_folder = glob_hostile_extension_folder
    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    schemas_dir = extension_folder / "myextension/labextension/schemas/myextension"
    assert schemas_dir.is_dir(), f"{schemas_dir} was not created!"
    assert (schemas_dir / "plugin.json").exists(), (
        f"plugin.json was not copied; {schemas_dir} holds "
        f"{sorted(path.name for path in schemas_dir.iterdir())}"
    )


def test_build_fails_when_no_remote_entry_is_produced(extension_folder):
    """The build must fail loudly rather than record `_build.load` as `"static"`.

    `path.posix.join("static", "")` evaluates to `"static"`, which is exactly
    the unusable value reported in
    https://github.com/jupyterlab/jupyter-builder/issues/163. Fixing the glob
    removes the known cause, but any future cause -- a renamed module
    federation entry, an emptied output directory -- would silently emit the
    same broken extension, so the builder reports a compilation error instead.

    Redirects rspack's output away from `static/` through the `webpackConfig`
    opt-in, which leaves the compilation itself successful but produces no
    `remoteEntry.*.js` for the cleanup plugin to record.
    """
    elsewhere = (extension_folder / "elsewhere").as_posix()
    (extension_folder / "webpack.config.js").write_text(
        f"module.exports = {{ output: {{ path: {json.dumps(elsewhere)} }} }};\n",
    )
    package_json_path = extension_folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data["jupyterlab"]["webpackConfig"] = "webpack.config.js"
    package_json_path.write_text(json.dumps(package_data, indent=2))

    result = run(
        ["jupyter-builder", "build", str(extension_folder)],
        cwd=extension_folder,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"Build succeeded despite producing no remoteEntry file!\nOutput:\n{output}"
    )
    assert "remoteEntry" in output, (
        f"Build failed without reporting the missing entry point!\nOutput:\n{output}"
    )

    build_data = json.loads(
        (extension_folder / "myextension/labextension/package.json").read_text(),
    )["jupyterlab"]
    assert build_data.get("_build", {}).get("load") != "static", (
        "The unusable `_build.load` value from issue 163 was written anyway!"
    )


@pytest.mark.parametrize("config_key", ["rspackConfig", "webpackConfig"])
def test_custom_config_is_honoured_under_either_key(extension_folder, config_key):
    """Both webpackConfig and rspackConfig must access rspack identically."""
    elsewhere = (extension_folder / "elsewhere").as_posix()
    (extension_folder / "custom.config.js").write_text(
        f"module.exports = {{ output: {{ path: {json.dumps(elsewhere)} }} }};\n",
    )
    package_json_path = extension_folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data["jupyterlab"][config_key] = "custom.config.js"
    package_json_path.write_text(json.dumps(package_data, indent=2))

    result = run(
        ["jupyter-builder", "build", str(extension_folder)],
        cwd=extension_folder,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"Custom config under {config_key!r} was ignored!\nOutput:\n{output}"
    )
    assert "remoteEntry" in output, (
        f"Custom config under {config_key!r} never reached rspack!\nOutput:\n{output}"
    )
    assert "deprecated" not in output, (
        f"webpackConfig must not warn at build time!\nOutput:\n{output}"
    )


def test_rspack_config_takes_precedence_over_webpack_config(extension_folder):
    """When both keys are set, ensure we only read rspackConfig."""
    elsewhere = (extension_folder / "elsewhere").as_posix()
    (extension_folder / "rspack.config.js").write_text(
        f"module.exports = {{ output: {{ path: {json.dumps(elsewhere)} }} }};\n",
    )
    # Throws if read, so picking the wrong key is unmistakable.
    (extension_folder / "webpack.config.js").write_text(
        "throw new Error('the webpackConfig key was read');\n",
    )
    package_json_path = extension_folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data["jupyterlab"]["rspackConfig"] = "rspack.config.js"
    package_data["jupyterlab"]["webpackConfig"] = "webpack.config.js"
    package_json_path.write_text(json.dumps(package_data, indent=2))

    result = run(
        ["jupyter-builder", "build", str(extension_folder)],
        cwd=extension_folder,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    assert "the webpackConfig key was read" not in output, (
        f"webpackConfig was read even though rspackConfig was set!\nOutput:\n{output}"
    )


def test_build_succeeds_without_dependencies_field(extension_folder):
    """Regression test for https://github.com/jupyterlab/jupyter-builder/issues/182.

    An extension whose package.json does not declare runtime `dependencies`
    (e.g., pure theme or minimal extensions) must build without TypeError.
    """
    package_json_path = extension_folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data.pop("dependencies", None)
    package_json_path.write_text(json.dumps(package_data, indent=2))

    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"
    assert (folder_path / "package.json").exists()


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


# Global defined by `@module-federation/runtime-core`, which only version 2
# (`rspack.container.ModuleFederationPlugin`) bundles; the webpack-compatible
# `ModuleFederationPluginV1` emits webpack's own sharing runtime instead.
MF_RUNTIME_MARKER = "__FEDERATION__"


def _uses_mf_runtime(extension_folder):
    """Whether the built extension bundles the Module Federation runtime."""
    static_dir = extension_folder / "myextension/labextension/static"
    return any(
        MF_RUNTIME_MARKER in path.read_text(encoding="utf-8") for path in static_dir.glob("*.js")
    )


def _set_package_mf_version(extension_folder, version):
    package_json_path = extension_folder / "package.json"
    package_data = json.loads(package_json_path.read_text())
    package_data["jupyterlab"]["moduleFederationVersion"] = version
    package_json_path.write_text(json.dumps(package_data, indent=2))


@pytest.mark.parametrize(
    ("package_version", "cli_version", "expect_mf_runtime"),
    [
        pytest.param(None, None, False, id="default-is-1"),
        pytest.param(None, "1", False, id="cli-1"),
        pytest.param(None, "2", True, id="cli-2"),
        pytest.param(2, None, True, id="package-2"),
        pytest.param(2, "1", False, id="cli-1-overrides-package-2"),
        pytest.param(1, "2", True, id="cli-2-overrides-package-1"),
    ],
)
def test_build_module_federation_version(
    extension_folder,
    package_version,
    cli_version,
    expect_mf_runtime,
):
    """The selected Module Federation plugin must build and be the one used.

    Runs the whole path: Python flag handling, Commander parsing, the
    `package.json` value and its precedence, and an actual rspack build with
    the chosen plugin.
    """
    if package_version is not None:
        _set_package_mf_version(extension_folder, package_version)
    cli_flag = [] if cli_version is None else ["--module-federation-version", cli_version]

    run(
        ["jupyter-builder", "build", *cli_flag, str(extension_folder)],
        cwd=extension_folder,
        check=True,
    )

    output_dir = extension_folder / "myextension/labextension"
    load = json.loads((output_dir / "package.json").read_text())["jupyterlab"]["_build"]["load"]
    assert (output_dir / load).exists(), f"{load} is missing from {output_dir}!"
    assert _uses_mf_runtime(extension_folder) == expect_mf_runtime, (
        f"Expected the Module Federation runtime to be "
        f"{'bundled' if expect_mf_runtime else 'absent'}!"
    )


def test_build_rejects_invalid_package_mf_version(extension_folder):
    _set_package_mf_version(extension_folder, 3)

    result = run(
        ["jupyter-builder", "build", str(extension_folder)],
        cwd=extension_folder,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0, f"Invalid moduleFederationVersion was accepted!\n{output}"
    assert "moduleFederationVersion" in output, f"Error does not name the field!\n{output}"


def test_files_build_jupyterlab_builder(jupyterlab_builder_extension_folder):
    extension_folder = jupyterlab_builder_extension_folder
    run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder, check=True)

    folder_path = extension_folder / "myextension/labextension"
    expected_files = ["static/style.js", "package.json"]
    for filename in expected_files:
        filepath = folder_path / filename
        assert filepath.exists(), f"File {filename} does not exist in {folder_path}!"


@pytest.mark.parametrize("command", ["build", "watch"])
def test_mf_version_refused_for_jupyterlab_builder(jupyterlab_builder_extension_folder, command):
    """@jupyterlab/builder has no such flag, so it must fail before running."""
    extension_folder = jupyterlab_builder_extension_folder
    result = run(
        [
            "jupyter-builder",
            command,
            "--module-federation-version",
            "1",
            str(extension_folder),
        ],
        cwd=extension_folder,
        check=False,
        capture_output=True,
        text=True,
        timeout=WATCH_INITIAL_BUILD_TIMEOUT,
    )

    assert result.returncode != 0
    assert "only supported by @jupyter/builder" in result.stderr, result.stderr


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


def test_builder_version_mismatch(mismatch_extension_folder):
    extension_folder = mismatch_extension_folder

    # Seed the core-meta cache for 4.5.x so the build resolves offline instead
    # of downloading from GitHub (which is rate-limited and flaky). The
    # dummy declares an incompatible @jupyterlab/builder range to trigger the
    # version mismatch error this test asserts on.
    _seed_core_meta_cache("4.5.x", "^4.5.9")

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
