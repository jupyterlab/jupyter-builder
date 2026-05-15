# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Script to bump the version of jupyter-builder."""

import json
from pathlib import Path

import click
from jupyter_releaser.util import get_version, run
from packaging.version import parse


def is_version(spec: str) -> bool:
    """Return True if spec is a valid version string."""
    try:
        parse(spec)
    except Exception:  # noqa: BLE001
        return False
    else:
        return True


def increment_version(current: str, spec: str) -> str:
    """Return the next version given the current version and a bump spec."""
    curr = parse(current)

    if spec == "major":
        return f"{curr.major + 1}.0.0a0"

    if spec == "minor":
        return f"{curr.major}.{curr.minor + 1}.0.0a0"

    if spec == "patch":
        return f"{curr.major}.{curr.minor}.{curr.micro + 1}"

    if spec == "release" and curr.pre:
        p, x = curr.pre
        if p == "a":
            p = "b"
        elif p == "b":
            p = "rc"
        elif p == "rc":
            p = None

        suffix = f"{p}{x}" if p else ""
        return f"{curr.major}.{curr.minor}.{curr.micro}{suffix}"

    if spec == "next":
        spec = f"{curr.major}.{curr.minor}."
        if curr.pre:
            p, x = curr.pre
            spec += f"{curr.micro}{p}{x + 1}"
        else:
            spec += f"{curr.micro + 1}"
        return spec

    msg = f"Unknown spec: {spec}"
    raise ValueError(msg)


def to_js_version(version: str) -> str:
    """Convert Python version to npm version.

    1.2.3a0 → 1.2.3-alpha.0
    """
    v = parse(version)

    base = f"{v.major}.{v.minor}.{v.micro}"

    if not v.pre:
        return base

    p, x = v.pre

    mapping = {
        "a": "alpha",
        "b": "beta",
        "rc": "rc",
    }

    tag = mapping.get(p, p)
    return f"{base}-{tag}.{x}"


@click.command()
@click.argument("spec")
@click.option("--skip-if-dirty", is_flag=True, default=False)
def bump(spec: str, skip_if_dirty: bool) -> None:
    """Bump the version of jupyter-builder."""
    status = run("git status --porcelain").strip()
    if status and not skip_if_dirty:
        msg = "Git working tree is dirty"
        raise RuntimeError(msg)

    current = get_version()

    new_version = spec if is_version(spec) else increment_version(current, spec)

    js_version = to_js_version(new_version)

    print(f"Bumping version: {current} → {new_version}")  # noqa: T201
    print(f"JS version: {js_version}")  # noqa: T201

    here = Path(__file__).parent.parent.resolve()

    for version_file in here.glob("jupyter_builder/_version.py"):
        content = version_file.read_text().splitlines()
        print("Before: ", content)  # noqa: T201
        variable, _ = content[0].split(" = ")

        if variable != "__version__":
            msg = f"Invalid version file: {version_file}"
            raise ValueError(msg)

        version_file.write_text(f'__version__ = "{new_version}"\n')
        content = version_file.read_text().splitlines()
        print("After: ", content)  # noqa: T201

    pkg_path = here / "package.json"

    if pkg_path.exists():
        data = json.loads(pkg_path.read_text())
        print("Before: ", data["version"])  # noqa: T201  
        data["version"] = js_version
        pkg_path.write_text(json.dumps(data, indent=2) + "\n")
        data = json.loads(pkg_path.read_text())
        print("After: ", data["version"])  # noqa: T201
    else:
        msg = "package.json not found"
        raise FileNotFoundError(msg)


if __name__ == "__main__":

    bump()
