# Jupyter Builder

[![Build](https://github.com/jupyterlab/jupyter-builder/actions/workflows/build.yml/badge.svg)](https://github.com/jupyterlab/jupyter-builder/actions/workflows/build.yml)
[![version on npm](https://img.shields.io/npm/v/@jupyter/builder.svg)](https://www.npmjs.com/package/@jupyter/builder)
[![version on PyPI](https://img.shields.io/pypi/v/jupyter-builder.svg)](https://pypi.org/project/jupyter-builder/)
[![version on conda-forge](https://img.shields.io/conda/vn/conda-forge/jupyter-builder.svg)](https://anaconda.org/conda-forge/jupyter-builder)

Build tools for JupyterLab extensions.

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

Install extension assets in development mode (analogous to `pip install -e`).

```bash
jupyter-builder develop --overwrite <path/to/extension>
```

### `watch`

Automatically rebuild development assets when source files change.

```bash
jupyter-builder watch <path/to/extension>
```

## `jlpm`

`jupyter-builder` ships `jlpm`, a Jupyter-aware Node.js package manager wrapper:

```bash
jlpm install
jlpm build
```

## Python API

```python
from jupyter_builder.federated_extensions import (
    build_labextension,
    develop_labextension_py,
    watch_labextension,
)

build_labextension("/path/to/extension")
develop_labextension_py("/path/to/extension", overwrite=True, symlink=True)
watch_labextension("/path/to/extension", labextensions_path=[...])
```

## Uninstall

```bash
pip uninstall jupyter_builder
```

## Credits

This package was initially created during [GSoC 2024](https://summerofcode.withgoogle.com) by [@cronan03](https://github.com/cronan03), mentored by [@fcollonval](https://github.com/fcollonval).
