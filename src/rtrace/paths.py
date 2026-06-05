"""Resolution of bundled-artifact paths.

All native artifacts live under a single install prefix, ``RTRACE_HOME``. When the
``RTRACE_HOME`` environment variable is set (the packaged/installed case) paths are
resolved against the bundle layout described in ``DISTRIBUTION.md``. When it is not
set (the in-repo developer case) paths fall back to the locations produced by the
existing developer build (``dev.sh`` / ``src/build.sh``).

Individual paths can always be overridden by their dedicated environment variable,
which takes precedence over both layouts.
"""
import os
from pathlib import Path

# Repository root, derived as <root>/src/rtrace/paths.py -> <root>.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def rtrace_home():
    """Return the install prefix, or None when running from a source checkout."""
    env = os.environ.get("RTRACE_HOME")
    return Path(env) if env else None


def _resolve(env_var, bundle_relpath, dev_path):
    """Resolve a single artifact path.

    Precedence: explicit ``env_var`` > bundle layout under ``RTRACE_HOME`` > the
    in-repo developer build location.
    """
    override = os.environ.get(env_var)
    if override:
        return Path(override)
    home = rtrace_home()
    if home is not None:
        return home / bundle_relpath
    return dev_path


def drrun():
    """Path to the DynamoRIO ``drrun`` launcher."""
    return _resolve(
        "RTRACE_DRRUN",
        "dynamorio/bin64/drrun",
        _REPO_ROOT / "submodules/dynamorio/build/bin64/drrun",
    )


def librtrace_so():
    """Path to the compiled DynamoRIO client (``librtrace.so``)."""
    return _resolve(
        "RTRACE_CLIENT",
        "lib/librtrace.so",
        _REPO_ROOT / "src/build/librtrace.so",
    )


def funseeker_bin():
    """Path to the FunSeeker boundary-detection executable."""
    return _resolve(
        "RTRACE_FUNSEEKER",
        "funseeker/FunSeeker",
        _REPO_ROOT / "submodules/FunSeeker/src/FunSeeker/bin/Release/net6.0/FunSeeker",
    )


def cache_dir():
    """Directory for cached boundary-detection results.

    Defaults to ``./.rtrace-cache`` in the current working directory; override with
    ``RTRACE_CACHE_DIR``.
    """
    return Path(os.environ.get("RTRACE_CACHE_DIR", ".rtrace-cache"))
