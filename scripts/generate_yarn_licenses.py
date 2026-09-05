# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

"""Generate the third-party license report for the vendored ``jupyter_builder/yarn.js``.

``yarn.js`` is a prebuilt upstream artifact: Yarn Berry bundles itself with esbuild, so
the ``JSONLicenseWebpackPlugin`` this project uses for webpack builds cannot see inside
it. Instead this script rebuilds the bundle from ``yarnpkg/berry`` at the tag matching
the vendored copy, with esbuild's ``metafile`` turned on, and reports the packages the
files listed in that metafile came from.

The list esbuild produces is the bundle's own contents, which is not the same thing as
the dependency closure of ``@yarnpkg/cli``, and the two differ in both directions.
``@yarnpkg/pnp`` declares ``arg`` and ``resolve.exports`` as devDependencies while
importing them from sources that are compiled in, so a closure walk misses code that
ships. A closure also carries packages no bundle can contain: type-only ``@types/*``
packages, ``tslib`` (esbuild inlines its own helpers rather than importing them), and
dependencies that no source file imports at all.

Three artifacts are written from that one file list, so they cannot drift apart:

* ``THIRD_PARTY_LICENSES/yarn.js.third-party-licenses.json`` -- the machine-readable
  report. Its schema deliberately matches the one emitted by
  ``JSONLicenseWebpackPlugin``

* ``THIRD_PARTY_LICENSES/yarn.js.LICENSE.txt`` -- the same data rendered in text form.
* the ``license`` field in ``pyproject.toml`` -- the aggregate SPDX expression, computed
  as the union of every ``licenseId`` in the report plus the licenses of the parts of
  this project that are not inside ``yarn.js``.

Usage::

    python scripts/generate_yarn_licenses.py 3.5.0
    python scripts/generate_yarn_licenses.py 3.5.0 --berry-checkout /path/to/berry
    python scripts/generate_yarn_licenses.py 3.5.0 --berry-checkout berry --metafile out.json

The last form reuses a metafile from a build that already happened, which is what CI
does: ``.github/workflows/verify-yarn-bundle.yml`` rebuilds the bundle to compare its
hash with the vendored copy, and that same build produces the file list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# The bundle vendored here is not a stock `@yarnpkg/cli` build: it additionally carries
# the workspace-tools plugin, because `jlpm` exposes `yarn workspaces foreach`. This
# mirrors the patch applied in .github/workflows/verify-yarn-bundle.yml, which verifies
# the vendored bundle is byte-for-byte reproducible; the two must stay in step.
EXTRA_BUNDLE_PLUGINS = ("@yarnpkg/plugin-workspace-tools",)

# Berry 3.5.0 asks for `esbuild-wasm@^0.15.5`, and the version its lockfile resolves to
# crashes on Node 18 and later. The workflow pins the same version for the same reason.
ESBUILD_WASM_VERSION = "0.15.18"

# The builder's esbuild call, and the two edits that make it write out the file list.
# `metafile: true` does not change the bundle it emits, so the same build still serves
# the byte-for-byte comparison the workflow makes.
BUILDER_SOURCE = Path("packages/yarnpkg-builder/sources/commands/build/bundle.ts")
BUILD_CALL_ANCHOR = "const res = await build({"
MINIFY_ANCHOR = "minify: !this.noMinify,"
# The loop appears twice, once per warning kind; the write goes in front of the first.
WARNINGS_ANCHOR = "for (const warning of res.warnings) {"

# Yarn maps every YARN_-prefixed variable onto a configuration key and aborts on the ones
# it does not know, so the variable naming the metafile must not carry that prefix.
METAFILE_ENV = "BUNDLE_METAFILE"
METAFILE_WRITE = (
    f"require('fs').writeFileSync(process.env.{METAFILE_ENV}, JSON.stringify(res.metafile));"
)

# An input inside a package taken from Yarn's cache. Both plain cache paths and the
# `__virtual__/<hash>/<n>/` ones esbuild reports for virtual instances end in the same
# `<archive>.zip/node_modules/<package>/` tail, so one pattern covers both. Matched
# before WORKSPACE_INPUT, because a package may itself ship a `sources/` directory.
CACHE_INPUT = re.compile(r"/(?P<archive>[^/]+\.zip)/node_modules/(?P<name>(?:@[^/]+/)?[^/]+)/")

# An input inside one of Berry's own workspaces, reported either as
# `../yarnpkg-core/sources/...` or as `.../1/packages/plugin-git/sources/...`.
WORKSPACE_INPUT = re.compile(r"(?:^|/)(?:packages/)?(?P<dir>[A-Za-z0-9][A-Za-z0-9._-]*)/sources/")

# esbuild reports the workspace it was pointed at with paths relative to it, so those
# inputs carry no directory to match on.
ENTRY_WORKSPACE = "yarnpkg-cli"

# Filename prefixes that hold license text, checked case-insensitively.
LICENSE_PREFIXES = ("LICENSE", "LICENCE", "COPYING")

# Licenses covering the parts of the distribution that are not inside yarn.js, and so
# are not discoverable by walking Berry's dependency tree. They still belong in the
# aggregate expression, which has to cover everything in the wheel.
OTHER_LICENSES = (
    "BSD-3-Clause",  # jupyter_builder itself, see LICENSE
    "MIT",  # the vendored jupyter_builder/jupyterlab_semver.py, see semver.LICENSE.txt
)

# npm manifests in the wild still carry SPDX identifiers that have since been
# deprecated. PEP 639 wants a currently-valid expression, so normalise them.
DEPRECATED_SPDX = {
    "GPL-2.0": "GPL-2.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-3.0": "LGPL-3.0-only",
}

LICENSE_DIR = Path("THIRD_PARTY_LICENSES")
DEFAULT_JSON_OUTPUT = LICENSE_DIR / "yarn.js.third-party-licenses.json"
DEFAULT_TEXT_OUTPUT = LICENSE_DIR / "yarn.js.LICENSE.txt"
DEFAULT_PYPROJECT = Path("pyproject.toml")

RULE = "-" * 78


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    """Run a command, streaming its output, and raise if it fails."""
    print(f"+ {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)  # noqa: S603


def capture(cmd: list[str], cwd: Path) -> str:
    """Run a command and return its stripped stdout."""
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def clone_berry(version: str, dest: Path) -> None:
    """Clone yarnpkg/berry at the tag matching ``version``."""
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            berry_tag(version),
            "https://github.com/yarnpkg/berry.git",
            str(dest),
        ],
        cwd=dest.parent,
    )


def berry_tag(version: str) -> str:
    """Return the Berry tag holding the sources for a given Yarn CLI version."""
    return f"@yarnpkg/cli/{version}"


def patch_cli_manifest(checkout: Path) -> None:
    """Add the extra plugins carried by the vendored bundle to the CLI manifest."""
    manifest_path = checkout / "packages" / "yarnpkg-cli" / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for plugin in EXTRA_BUNDLE_PLUGINS:
        manifest["dependencies"][plugin] = "workspace:^"
        bundled = manifest["@yarnpkg/builder"]["bundles"]["standard"]
        if plugin not in bundled:
            bundled.append(plugin)

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def verify_checkout(checkout: Path, version: str) -> None:
    """Fail if a reused checkout cannot produce what a fresh clone would.

    ``--berry-checkout`` skips both the clone and the CLI manifest patch, so the tree is
    whatever the caller left there: it may sit at the wrong tag, or lack the extra
    plugins the vendored bundle carries. Either would quietly yield a report that does
    not describe ``jupyter_builder/yarn.js``. Checked before anything is built, so a
    checkout that cannot give a faithful answer fails in seconds.
    """
    tag = berry_tag(version)
    try:
        expected = capture(["git", "rev-parse", f"{tag}^{{commit}}"], cwd=checkout)
    except subprocess.CalledProcessError:
        msg = f"{checkout} has no {tag} tag; fetch it, or drop --berry-checkout to clone"
        raise RuntimeError(msg) from None

    head = capture(["git", "rev-parse", "HEAD"], cwd=checkout)
    if head != expected:
        msg = (
            f"{checkout} is at {head[:12]}, not {tag} ({expected[:12]}); "
            f"check out the tag, or drop --berry-checkout to clone"
        )
        raise RuntimeError(msg)

    manifest_path = checkout / "packages" / "yarnpkg-cli" / "package.json"
    dependencies = json.loads(manifest_path.read_text(encoding="utf-8"))["dependencies"]
    absent = [p for p in EXTRA_BUNDLE_PLUGINS if p not in dependencies]
    if absent:
        msg = (
            f"{manifest_path} does not depend on {', '.join(absent)}, which the vendored "
            f"bundle carries, so the report would understate it. Apply the same patch "
            f"patch_cli_manifest() makes, or drop --berry-checkout to clone"
        )
        raise RuntimeError(msg)


def patch_builder_manifest(checkout: Path) -> None:
    """Pin the esbuild build the bundler runs on, so it works on current Node."""
    manifest_path = checkout / "packages" / "yarnpkg-builder" / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependencies"]["esbuild"] = f"npm:esbuild-wasm@{ESBUILD_WASM_VERSION}"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def patch_builder_metafile(checkout: Path) -> None:
    """Make Berry's builder write esbuild's metafile to ``$BUNDLE_METAFILE``.

    Also called from the workflow, so the build that checks the bundle's hash is the one
    that produces the file list. Doing nothing when the patch is already applied keeps
    that call safe to repeat.
    """
    path = Path(checkout) / BUILDER_SOURCE
    source = path.read_text(encoding="utf-8")
    if METAFILE_WRITE in source:
        return

    for anchor, expected in ((BUILD_CALL_ANCHOR, 1), (MINIFY_ANCHOR, 1), (WARNINGS_ANCHOR, 2)):
        if source.count(anchor) != expected:
            msg = (
                f"{path} has {source.count(anchor)} occurrences of {anchor!r}, expected "
                f"{expected}; upstream changed the builder and this patch needs rewriting"
            )
            raise RuntimeError(msg)

    source = source.replace(MINIFY_ANCHOR, f"{MINIFY_ANCHOR}\n          metafile: true,", 1)
    source = source.replace(WARNINGS_ANCHOR, f"{METAFILE_WRITE}\n        {WARNINGS_ANCHOR}", 1)
    path.write_text(source, encoding="utf-8")


def yarn(checkout: Path, args: list[str], env: dict[str, str] | None = None) -> None:
    """Run Berry's own Yarn inside a checkout, on the PnP linker it is set up for."""
    run(
        ["node", "scripts/run-yarn.js", *args],
        cwd=checkout,
        env={**os.environ, "YARN_NODE_LINKER": "pnp", **(env or {})},
    )


def install_build_deps(checkout: Path) -> None:
    """Install what building the CLI bundle needs, and nothing more.

    Berry is a zero-install PnP repo. Focusing on the two workspaces the build touches
    skips the rest of the monorepo, which otherwise compiles the website's native image
    tooling for nothing.
    """
    yarn(
        checkout,
        ["workspaces", "focus", "@yarnpkg/cli", "@yarnpkg/builder"],
        {"YARN_ENABLE_IMMUTABLE_INSTALLS": "false"},
    )


def build_bundle(checkout: Path, metafile: Path) -> None:
    """Build the CLI bundle, writing esbuild's file list to ``metafile``."""
    yarn(
        checkout,
        ["workspace", "@yarnpkg/cli", "run", "build:cli", "--no-git-hash"],
        {METAFILE_ENV: str(metafile.resolve())},
    )


def license_id(manifest: dict[str, Any]) -> str:
    """Extract an SPDX identifier from a package manifest, or '' if absent."""
    license_field = manifest.get("license")
    if isinstance(license_field, str):
        return license_field
    # Deprecated npm formats, still seen in older transitive dependencies.
    if isinstance(license_field, dict):
        return str(license_field.get("type", ""))
    licenses = manifest.get("licenses")
    if isinstance(licenses, list):
        types = [entry.get("type", "") for entry in licenses if isinstance(entry, dict)]
        return " OR ".join(t for t in types if t)
    return ""


def license_text(names: Iterable[str], read: Callable[[str], bytes]) -> str:
    """Concatenate the license files among ``names``, or return '' if there are none.

    A package may ship several (dual-licensed ones often do), so none is dropped, and
    the shortest name comes first, putting a plain LICENSE before LICENSE-MIT. Newlines
    are normalised the way ``Path.read_text`` normalises them, so a package gives the
    same bytes whether it is read from a directory or from a cache archive.
    """
    chosen = sorted(
        (name for name in names if name.upper().startswith(LICENSE_PREFIXES)),
        key=lambda name: (len(name), name),
    )
    texts = [
        read(name)
        .decode("utf-8", errors="replace")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
        for name in chosen
    ]
    return "\n\n".join(text for text in texts if text)


def license_record(manifest: dict[str, Any], text: str) -> dict[str, str]:
    """Build one report entry, in the schema ``JSONLicenseWebpackPlugin`` emits."""
    return {
        "name": manifest["name"],
        "versionInfo": str(manifest.get("version", "")),
        "licenseId": license_id(manifest),
        "extractedText": text,
    }


def read_cached_package(archives: dict[str, Path], archive_name: str, name: str) -> dict[str, str]:
    """Read one package's manifest and license text out of its cache archive."""
    archive_path = archives.get(archive_name)
    if archive_path is None:
        msg = (
            f"{archive_name} is named in the metafile but is not in the checkout's cache; "
            f"the metafile and the checkout come from different installs"
        )
        raise RuntimeError(msg)

    with zipfile.ZipFile(archive_path) as archive:
        prefix = f"node_modules/{name}/"
        root = [
            member[len(prefix) :]
            for member in archive.namelist()
            if member.startswith(prefix) and "/" not in member[len(prefix) :]
        ]
        manifest = json.loads(archive.read(f"{prefix}package.json"))
        return license_record(manifest, license_text(root, lambda m: archive.read(prefix + m)))


def read_workspace(checkout: Path, directory: str, root_license: str) -> dict[str, str]:
    """Read one Berry workspace's manifest and license text.

    Most workspaces ship no license file and fall under the repository-root license, but
    a few carry their own. ``plugin-patch`` keeps the notice for the patch-applying code
    it derives from, and that notice is the one that has to be reproduced.
    """
    package_dir = checkout / "packages" / directory
    manifest = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    names = [entry.name for entry in package_dir.iterdir() if entry.is_file()]
    text = license_text(names, lambda name: (package_dir / name).read_bytes())
    return license_record(manifest, text or root_license)


def build_report(metafile: dict[str, Any], checkout: Path) -> tuple[dict[str, Any], list[str]]:
    """Build the license report from the file list esbuild produced.

    Every file esbuild resolved is counted, rather than only the ones it reports as
    contributing bytes to the output. For this bundle the two sets are the same, and
    where they could differ, naming a package that was dropped is the safer mistake.

    Returns the report and the list of ``name@version`` entries with no license text,
    so a human can review them.
    """
    archives = {path.name: path for path in (checkout / ".yarn" / "cache").glob("*.zip")}
    root_license = (checkout / "LICENSE.md").read_text(encoding="utf-8").strip()

    packages: dict[tuple[str, str], dict[str, str]] = {}
    seen_cached: set[tuple[str, str]] = set()
    seen_workspaces: set[str] = set()

    for path in metafile["inputs"]:
        cached = CACHE_INPUT.search(path)
        if cached:
            key = (cached["archive"], cached["name"])
            if key in seen_cached:
                continue
            seen_cached.add(key)
            record = read_cached_package(archives, *key)
        else:
            workspace = WORKSPACE_INPUT.search(path)
            directory = workspace["dir"] if workspace else ENTRY_WORKSPACE
            if directory in seen_workspaces:
                continue
            seen_workspaces.add(directory)
            record = read_workspace(checkout, directory, root_license)

        packages.setdefault((record["name"], record["versionInfo"]), record)

    ordered = sorted(packages.values(), key=lambda p: (p["name"], p["versionInfo"]))
    missing = [f"{p['name']}@{p['versionInfo']}" for p in ordered if not p["extractedText"]]
    return {"packages": ordered}, missing


def normalize_spdx(expression: str) -> str:
    """Replace deprecated SPDX identifiers in a single package's license expression."""
    return re.sub(
        r"[A-Za-z0-9.+-]+",
        lambda m: DEPRECATED_SPDX.get(m.group(0), m.group(0)),
        expression,
    )


def aggregate_expression(license_ids: Iterable[str]) -> str:
    """Combine per-package license ids into one SPDX expression covering all of them.

    Simple identifiers are ANDed together in alphabetical order. A package offering a
    choice of licenses contributes a parenthesised ``OR`` group, kept intact and placed
    last so the result stays readable.
    """
    simple: set[str] = set()
    compound: set[str] = set()
    for raw in license_ids:
        value = normalize_spdx(raw.strip().strip("()").strip())
        if not value:
            continue
        if " " in value:
            compound.add(f"({value})")
        else:
            simple.add(value)
    return " AND ".join([*sorted(simple), *sorted(compound)])


def render_text(report: dict[str, Any], version: str, commit: str, expression: str) -> str:
    """Render the human-readable license file from the machine-readable report."""
    packages = report["packages"]
    bundle_expression = aggregate_expression(p["licenseId"] for p in packages)
    lines = [
        "Third-party licenses for jupyter_builder/yarn.js",
        "",
        "jupyter_builder/yarn.js is a vendored copy of the Yarn CLI bundle.",
        "",
        "    Upstream repository: https://github.com/yarnpkg/berry",
        f"    Tag:                 {berry_tag(version)}",
        f"    Commit:              {commit}",
        "    npm package:         @yarnpkg/cli",
        f"    Version:             {version}",
        "",
        "THIS FILE IS GENERATED -- do not edit it by hand. It is rendered from",
        "yarn.js.third-party-licenses.json by scripts/generate_yarn_licenses.py; run",
        "the generator again instead, so the two files cannot disagree.",
        "",
        "The JSON report next to this file carries the same information in a",
        "machine-readable form, including the exact version of every package, for",
        "downstream packagers that need it.",
        "",
        f"Packages: {len(packages)}",
        f"Aggregate license expression for this bundle: {bundle_expression}",
        "",
    ]
    if expression != bundle_expression:
        # The distribution also contains code that is not part of yarn.js.
        lines += [
            "The expression recorded in the project metadata additionally covers the",
            f"rest of the distribution: {expression}",
            "",
        ]

    for package in packages:
        lines += [
            RULE,
            "",
            f"{package['name']} {package['versionInfo']}".rstrip(),
            f"SPDX-License-Identifier: {package['licenseId'] or 'unknown'}",
            "",
        ]
        if package["extractedText"]:
            lines.append(package["extractedText"])
        else:
            lines.append(
                "This package ships no license file; the identifier above is the one "
                "declared\nin its package.json.",
            )
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def update_pyproject(path: Path, expression: str) -> str:
    """Rewrite the ``license`` field in pyproject.toml, returning the previous value."""
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(r'^license = "(?P<value>[^"]*)"$', re.MULTILINE)
    matches = pattern.findall(content)
    if len(matches) != 1:
        msg = f"expected exactly one top-level license field in {path}, found {len(matches)}"
        raise RuntimeError(msg)
    path.write_text(pattern.sub(f'license = "{expression}"', content), encoding="utf-8")
    return str(matches[0])


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="bundled Yarn version, e.g. 3.5.0")
    parser.add_argument(
        "--berry-checkout",
        type=Path,
        help="reuse an existing Berry checkout at this path instead of cloning; "
        "it must sit at the matching tag and carry the bundle's extra plugins",
    )
    parser.add_argument(
        "--metafile",
        type=Path,
        help="reuse the esbuild metafile from a build that already happened, instead of "
        "building the bundle again; requires --berry-checkout to be the tree it was "
        "built from",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help=f"machine-readable report path (default: {DEFAULT_JSON_OUTPUT})",
    )
    parser.add_argument(
        "--text-output",
        type=Path,
        default=DEFAULT_TEXT_OUTPUT,
        help=f"human-readable report path (default: {DEFAULT_TEXT_OUTPUT})",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=DEFAULT_PYPROJECT,
        help=f"project metadata to update the SPDX expression in (default: {DEFAULT_PYPROJECT})",
    )
    args = parser.parse_args()
    if args.metafile and not args.berry_checkout:
        parser.error("--metafile needs --berry-checkout, the tree the metafile was built from")
    return args


def main() -> int:
    """Generate the report and write it to disk."""
    args = parse_args()

    temp_dir: str | None = None
    try:
        if args.berry_checkout:
            checkout = args.berry_checkout
            verify_checkout(checkout, args.version)
        else:
            temp_dir = tempfile.mkdtemp(prefix="berry-licenses-")
            checkout = Path(temp_dir) / "berry"
            clone_berry(args.version, checkout)
            patch_cli_manifest(checkout)

        metafile_path = args.metafile
        if metafile_path is None:
            # Everything the build needs, applied to whichever checkout we ended up with.
            # The install runs every time rather than only when one is missing, so a tree
            # left over from an earlier run cannot answer for a manifest it predates.
            patch_builder_manifest(checkout)
            patch_builder_metafile(checkout)
            install_build_deps(checkout)
            metafile_path = checkout / "metafile.json"
            build_bundle(checkout, metafile_path)

        metafile = json.loads(metafile_path.read_text(encoding="utf-8"))
        commit = capture(["git", "rev-parse", "HEAD"], cwd=checkout)
        report, missing = build_report(metafile, checkout)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    expression = aggregate_expression(
        [*OTHER_LICENSES, *(p["licenseId"] for p in report["packages"])],
    )

    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.text_output.write_text(
        render_text(report, args.version, commit, expression),
        encoding="utf-8",
    )
    previous = update_pyproject(args.pyproject, expression)

    print(f"{len(report['packages'])} packages", file=sys.stderr)
    print(f"wrote {args.json_output}", file=sys.stderr)
    print(f"wrote {args.text_output}", file=sys.stderr)
    print(f"\nSPDX expression\n  before: {previous}\n  after:  {expression}", file=sys.stderr)
    if missing:
        print(
            f"\n{len(missing)} package(s) ship no license text; review these by hand:",
            file=sys.stderr,
        )
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
