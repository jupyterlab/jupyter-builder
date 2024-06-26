# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from copier import run_copy

def test_tpl():
    assert True

def helper(dest):
   run_copy("https://github.com/jupyterlab/extension-template.git", dest, 
            data={"kind": "frontend", "author_name": "tester"}, unsafe=True)

def test_dummy(tmp_path):
     extension_folder  = tmp_path / "ext"
     extension_folder.mkdir()
     helper(str(extension_folder))
# Or from a Git URL.

