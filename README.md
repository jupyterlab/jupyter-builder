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

| Flag                                 | Description                                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `--development`                      | Build in development mode (default: `False`)                                                      |
| `--source-map`                       | Generate source maps (default: `False`)                                                           |
| `--static-url=<url>`                 | Set the URL for static assets                                                                     |
| `--core-version=<version>`           | JupyterLab core version to build against                                                          |
| `--core-package-file=<path>`         | Path to a core application `package.json` (overrides `--core-version`)                            |
| `--module-federation-version=<1\|2>` | Module Federation runtime version (default: `1`, see [below](#module-federation-runtime-version)) |

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

| Flag                                 | Description                                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `--development`                      | Build in development mode (default: `True`)                                                       |
| `--source-map`                       | Generate source maps (default: `False`)                                                           |
| `--core-version=<version>`           | JupyterLab core version to build against                                                          |
| `--core-package-file=<path>`         | Path to a core application `package.json` (overrides `--core-version`)                            |
| `--module-federation-version=<1\|2>` | Module Federation runtime version (default: `1`, see [below](#module-federation-runtime-version)) |

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
    module_federation_version=None,
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
    module_federation_version=None,
)
```

### Module Federation runtime version

Extensions are built with **Module Federation 1** — the webpack-compatible runtime — by
default. Module Federation 2 can be opted into per build:

```bash
jupyter-builder build --module-federation-version 2 /path/to/extension
```

or per extension, in the extension's `package.json`:

```json
{
  "jupyterlab": {
    "moduleFederationVersion": 2
  }
}
```

The `--module-federation-version` flag takes precedence over the `package.json` value; if
neither is set the default of `1` applies.

**Why 2 is opt-in.** JupyterLab shares its core packages with `import: false`, meaning no
fallback copy is bundled into the extension. For core packages that are *not* listed in
JupyterLab's `singletonPackages` — `@jupyterlab/docregistry`, for example — the MF2 runtime
fails hard when no version in the share scope satisfies the extension's `requiredVersion`,
because there is no bundled fallback to fall back to. MF1 keeps webpack's behaviour of
warning and using whatever version the host provides, which is what allows an extension
built against one JupyterLab minor version to load in the next.

Until that gap is closed upstream
([module-federation/core#4651](https://github.com/module-federation/core/issues/4651)),
version 2 is only safe for extensions that do not consume such packages. Setting it is a
good way to test whether MF2 works for your extension, but MF1 remains the supported
default.

### Environment variables

jupyter-builder supports the following environment variables to override network URLs —
for example, to point at an internal mirror or a local proxy. A warning is emitted at startup
whenever a variable is set.

| Variable               | Default                             | Purpose                                                           |
| ---------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `JPBLD_NPM_URL`        | `https://registry.npmjs.org`        | npm registry used to resolve and download `@jupyterlab/core-meta` |
| `JPBLD_RAW_GITHUB_URL` | `https://raw.githubusercontent.com` | Raw GitHub content URL used as a fallback when npm is unavailable |

**Example — redirect to a corporate npm mirror:**

```bash
export JPBLD_NPM_URL=https://npm.internal.example.com
jupyter-builder build /path/to/extension
```

**Core metadata resolution order**

When no explicit `--core-version` is given, jupyter-builder looks for
`@jupyterlab/core-meta` in the extension's `node_modules` first (no network
required). If the package is not found there a warning is printed and the
metadata is fetched from the npm registry, falling back to raw GitHub if npm
is unreachable.

## Uninstall

```bash
pip uninstall jupyter_builder
```

## Credits

This package was initially created during [GSoC 2024](https://summerofcode.withgoogle.com) by [@cronan03](https://github.com/cronan03), mentored by [@fcollonval](https://github.com/fcollonval).
