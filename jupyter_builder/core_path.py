

from pathlib import Path


def default_core_path() -> str:
    import jupyterlab
    return str(Path(jupyterlab.__file__).parent / "staging")