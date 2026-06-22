# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import re
from pathlib import Path


def test_source_map_loader_excludes_module_federation_in_source():
    """Regression test for https://github.com/jupyterlab/jupyter-builder/issues/111.

    @module-federation/error-codes@0.21.4 shipped source map files that
    referenced TypeScript source files (e.g. src/error-codes.ts) which were
    never included in the published package. This caused source-map-loader to
    throw ENOENT warnings during extension builds.

    The fix adds an exclude rule in extensionConfig.ts so that source-map-loader
    skips the @module-federation directory entirely.
    """
    config_path = Path(__file__).parent.parent / "src" / "extensionConfig.ts"
    content = config_path.read_text()

    assert "@module-federation" in content, (
        "Expected an exclude rule for @module-federation in extensionConfig.ts. "
        "This guard prevents source-map-loader from throwing ENOENT warnings "
        "when @module-federation packages ship source maps without the original "
        "source files (regression: issue #111)."
    )


def test_source_map_loader_exclude_rule_is_in_compiled_output():
    """Verify the exclude rule survives TypeScript compilation.

    Checks the compiled lib/extensionConfig.js to ensure the
    @module-federation exclude pattern is present in the actual
    output that gets used at runtime.
    """
    compiled_path = Path(__file__).parent.parent / "lib" / "extensionConfig.js"
    assert compiled_path.exists(), (
        "lib/extensionConfig.js not found. Run 'yarn build:lib' first."
    )
    content = compiled_path.read_text()

    assert "@module-federation" in content, (
        "The @module-federation exclude rule is missing from the compiled output. "
        "This means the fix in extensionConfig.ts was not compiled correctly."
    )


def test_source_map_loader_exclude_rule_is_paired_with_loader():
    """Verify the exclude rule appears alongside the source-map-loader rule.

    Ensures the exclude is not just mentioned anywhere in the file but is
    actually part of the source-map-loader configuration block.
    """
    config_path = Path(__file__).parent.parent / "src" / "extensionConfig.ts"
    content = config_path.read_text()

    # Find the source-map-loader block and check exclude is within 5 lines of it
    lines = content.splitlines()
    loader_line = next(
        (i for i, line in enumerate(lines) if "source-map-loader" in line), None
    )
    assert loader_line is not None, "source-map-loader rule not found in extensionConfig.ts"

    nearby = "\n".join(lines[loader_line : loader_line + 5])
    assert "@module-federation" in nearby, (
        "The @module-federation exclude rule is not adjacent to the "
        "source-map-loader rule. It may have been misplaced."
    )
