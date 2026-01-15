"""Pull in core client features.""" 

import importlib.metadata

from mpcontribs.client.core import Client
from mpcontribs.client.exceptions import MPContribsClientError
from mpcontribs.client.settings import MPCC_SETTINGS


try:
    __version__ = importlib.metadata.version("mpcontribs-client")
except Exception:
    # package is not installed
    pass

