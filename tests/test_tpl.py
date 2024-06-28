# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


from copier import run_copy

from subprocess import run





def test_tpl():
    assert True

def helper(dest):
#     run_copy(
#        "https://github.com/jupyterlab/extension-template",
#        dest,
#        defaults=True,
#        data={"author_name": "tester", "repository": "dummy"},
#        unsafe=True,
#        overwrite = True,
#        quiet = True
#    )
    run(["copier", "copy", "--trust", "-l", "-d" ,
          "author_name=tester", "-d", "repository=dummy",
            "https://github.com/jupyterlab/extension-template"
            ,dest], cwd=dest,
              check=True)

def test_dummy(tmp_path):
     extension_folder  = tmp_path / "ext"
     extension_folder.mkdir()
     helper(str(extension_folder))
# Or from a Git URL.

