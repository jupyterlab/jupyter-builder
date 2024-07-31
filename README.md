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


---

## GSoC 2024 Anecdote by [@cronan03](https://github.com/cronan03)
## Goal
The goals of this project are:
- to extract that tooling as a new separate package to ease maintenance (for core and extension developers)
- update the existing package to use the new one
- make it configurable to be reused for other applications.
  
## What I did
1. Successfully created a CLI with the processes `develop`, `build` and `watch` mentioned above.
2. Created extensive unit tests using `Pytest` to ensure the processes run efficiently on any OS.
3. Reduced ecternal dependancies by bringing `jlpm` and `jupyterlab_semver` to the package.
4. Pre released the package. It can be found on Pypi here https://pypi.org/project/jupyter-builder/
5. Initiated a solution to the issue https://github.com/jupyterlab/jupyterlab/issues/13456
   
## What's left to do
1. We should bring `@jupyterlab/builder` within this package and make it generic.
For now the code lives there: https://github.com/jupyterlab/jupyterlab/tree/main/builder
2. https://github.com/jupyterlab/jupyter-builder/blob/fffb100fc57ecb147bface4441f91bfd0cb6ff9a/jupyter_builder/federated_extensions.py#L296 which is responsible for checking version overlap has been temporarily ignored to make the build feature work.

## Merged PRs
1. https://github.com/jupyterlab/jupyter-builder/pull/11
   - This PR focuses on extracting the `develop` feature which is responsible for installing the Jupyter extension JS assets in dev mode.
   - Considering the size of [labextension.py](https://github.com/jupyterlab/jupyterlab/blob/main/jupyterlab/labextensions.py), only features essential to Jupyter builder were added.
   - Each of the features will inherit from the class `BaseExtensionApp` present [here](https://github.com/jupyterlab/jupyter-builder/blob/main/jupyter_builder/base_extension_app.py)
   - The [federated_extensions.py](https://github.com/jupyterlab/jupyter-builder/blob/main/jupyter_builder/federated_extensions.py)  sets up and executes commands to build, develop and waatch a JupyterLab extension. It resolves paths, constructs the appropriate command-line arguments, and executes the build process using `subprocess.check_call`. Optional parameters allow for customization of the build process, including logging, development mode, and source map generation.
2. https://github.com/jupyterlab/jupyter-builder/pull/13
   - This PR focuses on extracting the `build` feature which is responsible for creating the Javascript assests which will be consumed by the Jupyter App.
   - It will always result in the creation of a file `static/style.js` in `<extension_folder>/myextension/labextension`.
   - Tests have been crafted using `Pytest` to check for the existence of files mentioned above on running the `build` command.
3. https://github.com/jupyterlab/jupyter-builder/pull/18
   - The `watch` feature on running will rebuild the JS assets on being triggered. This happens on changing contents in `<extension_folder>/src/index.ts`
   - To test this feature we deliberately make a change in `index.ts` triggering `watch`. This replaces old JS assets with new ones having different hash values in the file names. We create 2 vectors of filenames before and after triggering `watch` which will tell us if it actually worked.
4. https://github.com/jupyterlab/jupyter-builder/pull/20
   - To reduce external dependancies, we added `jlpm` to this package.
   - It existed [here](https://github.com/jupyterlab/jupyterlab/blob/main/jupyterlab/jlpmapp.py) with the [entrypoint](https://github.com/jupyterlab/jupyterlab/blob/e048f27548969c0e4403417ac04bc186f119128f/pyproject.toml#L60).
5. https://github.com/jupyterlab/jupyter-builder/pull/22
   - Documented the working of the Jupyter builder along with installation guide.
  
## Challenges and Learning
1. One of the main challenges was starting this project from scratch with no pre existing code to rely on. I thank my mentor [@fcollonval](https://github.com/fcollonval) for creating the skeleton in https://github.com/jupyterlab/jupyter-builder/pull/2 which gave me a base to work on.
2. Selecting relevant features for Jupyter builder from [labextension.py](https://github.com/jupyterlab/jupyterlab/blob/main/jupyterlab/labextensions.py) was relly tough without a thorough understanding on which functions Jupyter builder would actually rely on.
3. Creating tests for the `watch` feature was tricky as I had to carefully adjust sleep times to make sure the function was running before a change in `<extension_folder>/src/index.ts` was made. Otherwise the change happended before `watch` ran and never triggered it.
