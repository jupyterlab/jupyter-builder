# Jupyter Builder - GSoC 2024

Build tools for JupyterLab (and remixes)

> This _will_ start as an extraction of the builder tools currently included in
> the core [JupyterLab](https://github.com/jupyterlab/jupyterlab).

## Why extracting the build tools?

- This would also solve some chicken-and-egg problems like jupyterlab/jupyterlab_pygments#23.
- Isolating the builder functionalities will simplify the work
  of core and extension developers who can now focus on their respective parts of the
  codebase instead of the earlier intertwined code. It will in particular reduce the need to update the maintenance tooling to produce extension compatible with newer version of Jupyter app.

## How to install the package?

Execute the following command in a terminal:

```
pip install jupyter_builder
```

## What does it do?

- Provides a CLI for building Jupyter extensions. There are 3 subcommands
  - `build` : Builds the Jupyter extension JavaScript assets to be consumed by the Jupyter app.
    ```
    jupyter-builder build <path to extension folder>
    ```
  - `develop` : Install the Jupyter extension JavaScript assets in dev mode for consumption in the Jupyter app. It similar to [editable install mode of pip](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs)
    ```
    jupyter-builder develop --overwrite (path to extension folder)
    ```
  - `watch` : Automatically rebuild the development JavaScript assets when one file is changed to ease development.
    ```
    jupyter-builder watch (path to extension folder)
    ```
- Provides a NPM package manager: `jlpm`

## How to uninstall the package?

Execute the following command in a terminal:

```
pip uninstall jupyter_builder
```

See https://github.com/jupyterlab/jupyterlab/issues/13456
