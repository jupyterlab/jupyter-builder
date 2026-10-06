# Jupyter Builder

[![Jupyter Builder Tests](https://github.com/jupyterlab/jupyter-builder/actions/workflows/builder-tests.yml/badge.svg)](https://github.com/jupyterlab/jupyter-builder/actions/workflows/builder-tests.yml)
[![version on npm](https://img.shields.io/npm/v/@jupyter/builder.svg)](https://www.npmjs.com/package/@jupyter/builder)
[![version on PyPI](https://img.shields.io/pypi/v/jupyter-builder.svg)](https://pypi.org/project/jupyter-builder/)
[![version on conda-forge](https://img.shields.io/conda/vn/conda-forge/jupyter-builder.svg)](https://anaconda.org/conda-forge/jupyter-builder)

Build tools for JupyterLab extensions — extracted from the core [JupyterLab](https://github.com/jupyterlab/jupyterlab) codebase to be maintained and used independently.

## Installation

```bash
pip install jupyter_builder
```

## CLI

### `build`

Compile the extension JavaScript assets for consumption by a Jupyter app.

```bash
jupyter-builder build <path/to/extension>
```

### `develop`

Install extension assets in development mode (analogous to `pip install -e`). Uses a symlink by default.

```bash
jupyter-builder develop <path/to/extension>
```

### `watch`

Automatically rebuild development assets when source files change.

```bash
jupyter-builder watch <path/to/extension>
```

> For advanced configuration, see the [Advanced](#advanced) section for available flags.

## `jlpm`

`jupyter-builder` ships `jlpm`, a Jupyter-aware Node.js package manager wrapper:

```bash
jlpm install
jlpm build
```

## Advanced

### CLI flags

<details>
<summary><code>build</code></summary>

| Flag                         | Description                                                            |
| ---------------------------- | ---------------------------------------------------------------------- |
| `--development`              | Build in development mode (default: `False`)                           |
| `--source-map`               | Generate source maps (default: `False`)                                |
| `--static-url=<url>`         | Set the URL for static assets                                          |
| `--core-version=<version>`   | JupyterLab core version to build against                               |
| `--core-package-file=<path>` | Path to a core application `package.json` (overrides `--core-version`) |

</details>

<details>
<summary><code>develop</code></summary>

| Flag                         | Description                                  |
| ---------------------------- | -------------------------------------------- |
| `--overwrite`                | Overwrite existing files                     |
| `--user`                     | Install to the user's directory              |
| `--sys-prefix`               | Install under `sys.prefix` (default: `True`) |
| `--labextensions-dir=<path>` | Install to a custom labextensions directory  |

</details>

<details>
<summary><code>watch</code></summary>

| Flag                         | Description                                                            |
| ---------------------------- | ---------------------------------------------------------------------- |
| `--development`              | Build in development mode (default: `True`)                            |
| `--source-map`               | Generate source maps (default: `False`)                                |
| `--core-version=<version>`   | JupyterLab core version to build against                               |
| `--core-package-file=<path>` | Path to a core application `package.json` (overrides `--core-version`) |

</details>

### Python API

```python
from jupyter_builder.federated_extensions import (
    build_labextension,
    develop_labextension_py,
    watch_labextension,
)

build_labextension(
    "/path/to/extension",
    development=False,
    source_map=False,
    static_url=None,
    core_version=None,
    core_package_file=None,
)

develop_labextension_py(
    "/path/to/extension",
    overwrite=True,
    symlink=True,
    user=False,
    sys_prefix=True,
)

watch_labextension(
    "/path/to/extension",
    labextensions_path=[...],
    development=True,
    source_map=False,
)
```

### Environment variables

jupyter-builder supports the following environment variables to override network URLs —
for example, to point at an internal mirror or a local proxy — or to run in offline mode.
A warning is emitted at startup whenever a URL override variable is set.

| Variable               | Default                             | Purpose                                                                                                                                     |
| ---------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `JPBLD_NPM_URL`        | `https://registry.npmjs.org`        | npm registry used to resolve and download `@jupyterlab/core-meta`                                                                           |
| `JPBLD_RAW_GITHUB_URL` | `https://raw.githubusercontent.com` | Raw GitHub content URL used as a fallback when npm is unavailable                                                                           |
| `JPBLD_OFFLINE`        | `""` (unset)                        | Explicit offline mode (`1`, `true`, or `yes`). Disables network downloads and uses local cached or bundled `@jupyterlab/core-meta` metadata |

**Example — redirect to a corporate npm mirror:**

```bash
export JPBLD_NPM_URL=https://npm.internal.example.com
jupyter-builder build /path/to/extension
```

**Example — offline build:**

```bash
export JPBLD_OFFLINE=1
jupyter-builder build /path/to/extension
```

**Core metadata resolution order**

When resolving `@jupyterlab/core-meta`:

1. When no explicit `--core-version` is given, jupyter-builder looks for
   `@jupyterlab/core-meta` in the extension's `node_modules` first (no network
   required).
2. If the requested metadata version is already cached locally
   (`~/.cache/jupyterlab_builder/core/<version>/core.package.json`), the cached
   file is reused directly.
3. If `JPBLD_OFFLINE` is enabled (`1`, `true`, or `yes`), network access is prevented
   and jupyter-builder resolves against the bundled `core.package.json` shipped with the
   package (verifying version compatibility).
4. Otherwise, metadata is fetched from the npm registry (`JPBLD_NPM_URL`),
   falling back to raw GitHub (`JPBLD_RAW_GITHUB_URL`) if npm is unreachable.
5. If both npm and GitHub are unreachable (e.g., due to network failure),
   jupyter-builder falls back to the bundled `core.package.json` as a last resort.

## Uninstall

```bash
pip uninstall jupyter_builder
```

## Credits

This package was initially created during [GSoC 2024](https://summerofcode.withgoogle.com) by [@cronan03](https://github.com/cronan03), mentored by [@fcollonval](https://github.com/fcollonval).
