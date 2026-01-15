"""Set version for mpcontribs-io."""

from importlib.metadata import version

try:
    __version__ = version("mpcontribs-io")
except Exception:
    # package is not installed
    pass
