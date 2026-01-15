"""Define utility functions for MPContribs client."""

from __future__ import annotations

import gzip
from hashlib import md5
from jsonschema.exceptions import ValidationError
import orjson
import sys
from swagger_spec_validator.common import SwaggerValidationError
from typing import TYPE_CHECKING

from mpcontribs.client.exceptions import MPContribsClientError
from mpcontribs.client.settings import MPCC_SETTINGS

if TYPE_CHECKING:
    from typing import Any

_ipython = getattr(sys.modules.get("IPython"), "get_ipython", lambda: None)()


def _in_ipython() -> bool:
    """Check if running in IPython/Jupyter."""
    return _ipython is not None and "IPKernelApp" in getattr(_ipython, "config", {})


if _in_ipython():

    def _hide_traceback(
        exc_tuple=None,
        filename=None,
        tb_offset=None,
        exception_only=False,
        running_compiled_code=False,
    ):
        etype, value, tb = sys.exc_info()

        if issubclass(
            etype, (MPContribsClientError, SwaggerValidationError, ValidationError)
        ):
            return _ipython._showtraceback(
                etype, value, _ipython.InteractiveTB.get_exception_only(etype, value)
            )

        return _ipython._showtraceback(
            etype, value, _ipython.InteractiveTB(etype, value, tb)
        )

    _ipython.showtraceback = _hide_traceback


def _compress(data: Any) -> int | bytes:
    """Write JSONable data to gzipped bytes.

    Args:
        data (Any) : JSONable python object

    Returns:
        int : the length of the compressed data
        bytes : the compressed data
    """
    content = gzip.compress(orjson.dumps(data))
    return len(content), content


def _chunk_by_size(
    items: Any, max_size: float = 0.95 * MPCC_SETTINGS.MAX_BYTES
) -> bytes:
    """Compress a large data structure by chunks.

    Args:
        items (Any) : JSONable python object(s)

    Returns:
        bytes : the compressed data
    """
    buffer, buffer_size = [], 0

    for item in items:
        item_size = _compress(item)[0]

        if buffer_size + item_size <= max_size:
            buffer.append(item)
            buffer_size += item_size
        else:
            yield buffer
            buffer = [item]
            buffer_size = item_size

    if buffer_size > 0:
        yield buffer


def get_md5(d: dict[str, Any]) -> str:
    """Get the MD5 of a JSONable dict."""
    s = orjson.dumps({k: d[k] for k in sorted(d)})
    return md5(s).hexdigest()
