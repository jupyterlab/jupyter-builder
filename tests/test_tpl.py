# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


from copier import run_copy
from subprocess import run
import os

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

def test_files_build(tmp_path):
     extension_folder  = tmp_path / "ext"
     extension_folder.mkdir()
     helper(str(extension_folder))
     
     run(["jlpm" ,"install"], cwd=extension_folder, check=True)
     run(["jlpm" ,"run","build:prod"], cwd=extension_folder,check=True)
     
     run(["jupyter-builder", "build", str(extension_folder)], cwd=extension_folder,check=True)

     folder_path = extension_folder / "myextension/labextension"

     expected_files = ["static/style.js", "package.json"]

     for filename in expected_files:
       filepath = os.path.join(folder_path, filename)
       assert os.path.exists(filepath), f"File {filename} does not exist in {folder_path}!"
  
def test_files_build_development(tmp_path):
     extension_folder  = tmp_path / "ext"
     extension_folder.mkdir()
     helper(str(extension_folder))
     
     run(["jlpm" ,"install"], cwd=extension_folder, check=True)
     run(["jlpm" ,"run","build:prod"], cwd=extension_folder,check=True)
     
     run(["jupyter-builder", "build","--development","true", str(extension_folder)], cwd=extension_folder,check=True)
     
     folder_path = extension_folder / "myextension/labextension"

     expected_files = ["static/style.js", "package.json", "build_log.json"]

     for filename in expected_files:
       filepath = os.path.join(folder_path, filename)
       assert os.path.exists(filepath), f"File {filename} does not exist in {folder_path}!"


# def test_files_exist():
#   """
#   This test checks if a.py and b.py exist in a specific folder.
#   """

#   folder_path = r"D:/GSOC/JupyterBuild/jupyterlab-builder/tests/dummy/dummy1/labextension/static"

#   expected_files = ["style.js", "remoteEntry.cf9febd8c72130231294.js"]

#   for filename in expected_files:
#     filepath = os.path.join(folder_path, filename)
#     assert os.path.exists(filepath), f"File {filename} does not exist in {folder_path}!"
