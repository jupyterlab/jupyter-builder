
import inspect
import os
from pathlib import Path
import errno
import sys
import tempfile
from types import FrameType
import warnings

import platformdirs
pjoin = os.path.join

ENV_JUPYTER_PATH: list[str] = [str(Path(sys.prefix, "share", "jupyter"))]

##

# Capitalize Jupyter in paths only on Windows and MacOS (when not in Homebrew)
if sys.platform == "win32" or (
    sys.platform == "darwin" and not sys.prefix.startswith("/opt/homebrew")
):
    APPNAME = "Jupyter"
else:
    APPNAME = "jupyter"
##
def use_platform_dirs() -> bool:
    """Determine if platformdirs should be used for system-specific paths.

    We plan for this to default to False in jupyter_core version 5 and to True
    in jupyter_core version 6.
    """
    return envset("JUPYTER_PLATFORM_DIRS", False)  # type:ignore[return-value]


def _get_frame(level: int) -> FrameType | None:
    """Get the frame at the given stack level."""
    # sys._getframe is much faster than inspect.stack, but isn't guaranteed to
    # exist in all python implementations, so we fall back to inspect.stack()

    # We need to add one to level to account for this get_frame call.
    if hasattr(sys, "_getframe"):
        frame = sys._getframe(level + 1)
    else:
        frame = inspect.stack(context=0)[level + 1].frame
    return frame
# This function is from https://github.com/python/cpython/issues/67998
# (https://bugs.python.org/file39550/deprecated_module_stacklevel.diff) and
# calculates the appropriate stacklevel for deprecations to target the
# deprecation for the caller, no matter how many internal stack frames we have
# added in the process. For example, with the deprecation warning in the
# __init__ below, the appropriate stacklevel will change depending on how deep
# the inheritance hierarchy is.
def _external_stacklevel(internal: list[str]) -> int:
    """Find the stacklevel of the first frame that doesn't contain any of the given internal strings

    The depth will be 1 at minimum in order to start checking at the caller of
    the function that called this utility method.
    """
    # Get the level of my caller's caller
    level = 2
    frame = _get_frame(level)

    # Normalize the path separators:
    normalized_internal = [str(Path(s)) for s in internal]

    # climb the stack frames while we see internal frames
    while frame and any(s in str(Path(frame.f_code.co_filename)) for s in normalized_internal):
        level += 1
        frame = frame.f_back

    # Return the stack level from the perspective of whoever called us (i.e., one level up)
    return level - 1

def deprecation(message: str, internal: str | list[str] = "jupyter_core/") -> None:
    """Generate a deprecation warning targeting the first frame that is not 'internal'

    internal is a string or list of strings, which if they appear in filenames in the
    frames, the frames will be considered internal. Changing this can be useful if, for example,
    we know that our internal code is calling out to another library.
    """
    _internal: list[str]
    _internal = [internal] if isinstance(internal, str) else internal

    # stack level of the first external frame from here
    stacklevel = _external_stacklevel(_internal)

    # The call to .warn adds one frame, so bump the stacklevel up by one
    warnings.warn(message, DeprecationWarning, stacklevel=stacklevel + 1)

if use_platform_dirs():
    SYSTEM_JUPYTER_PATH = platformdirs.site_data_dir(
        APPNAME, appauthor=False, multipath=True
    ).split(os.pathsep)
else:
    deprecation(
        "Jupyter is migrating its paths to use standard platformdirs\n"
        "given by the platformdirs library.  To remove this warning and\n"
        "see the appropriate new directories, set the environment variable\n"
        "`JUPYTER_PLATFORM_DIRS=1` and then run `jupyter --paths`.\n"
        "The use of platformdirs will be the default in `jupyter_core` v6"
    )
    if os.name == "nt":
        programdata = os.environ.get("PROGRAMDATA", None)
        if programdata:
            SYSTEM_JUPYTER_PATH = [pjoin(programdata, "jupyter")]
        else:  # PROGRAMDATA is not defined by default on XP.
            SYSTEM_JUPYTER_PATH = [str(Path(sys.prefix, "share", "jupyter"))]
    else:
        SYSTEM_JUPYTER_PATH = [
            "/usr/local/share/jupyter",
            "/usr/share/jupyter",
        ]


##
def ensure_dir_exists(path: str | Path, mode: int = 0o777) -> None:
    """Ensure that a directory exists

    If it doesn't exist, try to create it, protecting against a race condition
    if another process is doing the same.
    The default permissions are determined by the current umask.
    """
    try:
        Path(path).mkdir(parents=True, mode=mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    if not Path(path).is_dir():
        raise OSError("%r exists but is not a directory" % path)

##
def jupyter_data_dir() -> str:
    """Get the config directory for Jupyter data files for this platform and user.

    These are non-transient, non-configuration files.

    Returns JUPYTER_DATA_DIR if defined, else a platform-appropriate path.
    """
    env = os.environ

    if env.get("JUPYTER_DATA_DIR"):
        return env["JUPYTER_DATA_DIR"]

    if use_platform_dirs():
        return platformdirs.user_data_dir(APPNAME, appauthor=False)

    home = get_home_dir()

    if sys.platform == "darwin":
        return str(Path(home, "Library", "Jupyter"))
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", None)
        if appdata:
            return str(Path(appdata, "jupyter").resolve())
        return pjoin(jupyter_config_dir(), "data")
    # Linux, non-OS X Unix, AIX, etc.
    xdg = env.get("XDG_DATA_HOME", None)
    if not xdg:
        xdg = pjoin(home, ".local", "share")
    return pjoin(xdg, "jupyter")

def use_platform_dirs() -> bool:
    """Determine if platformdirs should be used for system-specific paths.

    We plan for this to default to False in jupyter_core version 5 and to True
    in jupyter_core version 6.
    """
    return envset("JUPYTER_PLATFORM_DIRS", False)  # type:ignore[return-value]

def get_home_dir() -> str:
    """Get the real path of the home directory"""
    homedir = Path("~").expanduser()
    # Next line will make things work even when /home/ is a symlink to
    # /usr/home as it is on FreeBSD, for example
    return str(Path(homedir).resolve())

def jupyter_config_dir() -> str:
    """Get the Jupyter config directory for this platform and user.

    Returns JUPYTER_CONFIG_DIR if defined, otherwise the appropriate
    directory for the platform.
    """

    env = os.environ
    if env.get("JUPYTER_NO_CONFIG"):
        return _mkdtemp_once("jupyter-clean-cfg")

    if env.get("JUPYTER_CONFIG_DIR"):
        return env["JUPYTER_CONFIG_DIR"]

    if use_platform_dirs():
        return platformdirs.user_config_dir(APPNAME, appauthor=False)

    home_dir = get_home_dir()
    return pjoin(home_dir, ".jupyter")

_dtemps: dict[str, str] = {}

def _mkdtemp_once(name: str) -> str:
    """Make or reuse a temporary directory.

    If this is called with the same name in the same process, it will return
    the same directory.
    """
    try:
        return _dtemps[name]
    except KeyError:
        d = _dtemps[name] = tempfile.mkdtemp(prefix=name + "-")
        return d
    

