# Making a new release of jupyter_builder

The package can be published to `PyPI` manually or using the [Jupyter Releaser](https://github.com/jupyter-server/jupyter_releaser).

## Manual release

### Python package

This extension can be distributed as Python packages. All of the Python
packaging instructions are in the `pyproject.toml` file to wrap your extension in a
Python package. Before generating a package, you first need to install some tools:

```bash
pip install build twine hatch
```

Bump the version using `hatch`. By default this will create a tag.

```bash
hatch version <new-version>
```

You could also clean up the local git repository:

```bash
git clean -dfX
```

To create a Python source package (`.tar.gz`) and the binary package (`.whl`) in the `dist/` directory, do:

```bash
python -m build
```

> `python setup.py sdist bdist_wheel` is deprecated and will not work for this package.

Then to upload the package to PyPI, do:

```bash
twine upload dist/*
```

### NPM package

To publish the frontend part of the extension as a NPM package, do:

```bash
npm login
npm publish --access public
```

## Updating the vendored Yarn bundle

`jupyter_builder/yarn.js` is a prebuilt copy of the Yarn CLI, and its third-party
license report is generated. Vendoring a new bundle is therefore a two-part
change:

1. Replace `jupyter_builder/yarn.js`, and update `packageManager` in `package.json`
   and `BERRY_TAG` in `.github/workflows/verify-yarn-bundle.yml` to match.

1. Regenerate the license report and commit the result:

   ```bash
   python scripts/generate_yarn_licenses.py <new-yarn-version>
   ```

   This clones Berry at the matching tag, builds the bundle with esbuild's metafile
   turned on, and rewrites `THIRD_PARTY_LICENSES/yarn.js.third-party-licenses.json`,
   `THIRD_PARTY_LICENSES/yarn.js.LICENSE.txt` and the `license` SPDX expression in
   `pyproject.toml` from the one file list esbuild produces. It needs `node` and
   `git`, and takes about half a minute.

Which packages Yarn bundles, and under which licenses, changes between Yarn
releases, so skipping the regeneration leaves the distribution's license metadata
wrong. The `Verify vendored yarn.js` workflow enforces this: the build it already
runs to check the bundle's hash also emits the metafile, and the job then
regenerates the report from it and fails if the committed one differs.

## Automated releases with the Jupyter Releaser

The extension repository should already be compatible with the Jupyter Releaser. But
the GitHub repository and the package managers need to be properly set up. Please
follow the instructions of the Jupyter Releaser [checklist](https://jupyter-releaser.readthedocs.io/en/latest/how_to_guides/convert_repo_from_repo.html).

Here is a summary of the steps to cut a new release:

- Go to the Actions panel
- Run the "Step 1: Prep Release" workflow
- Check the draft changelog
- Run the "Step 2: Publish Release" workflow

> \[!NOTE\]
> Check out the [workflow documentation](https://jupyter-releaser.readthedocs.io/en/latest/get_started/making_release_from_repo.html)
> for more information.

## Publishing to `conda-forge`

If the package is not on conda forge yet, check the documentation to learn how to add it: https://conda-forge.org/docs/maintainer/adding_pkgs.html

Otherwise a bot should pick up the new version publish to PyPI, and open a new PR on the feedstock repository automatically.
