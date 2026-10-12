"""Kernel gateway config: structured (Datadog JSON) logging, see `mp_logging`.

Loaded by `jupyter kernelgateway` from `JUPYTER_CONFIG_DIR` (set in the
Dockerfile to this file's directory).
"""

import os
import sys

# mp_logging is copied next to this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mp_logging import HANDLER, build_logging_config  # noqa: E402

c = get_config()  # noqa: F821

_logging = build_logging_config(
    app_loggers=("KernelGatewayApp",),
    extra_loggers={
        # tornado's request log (logs successes at INFO, 4xx at WARNING, 5xx at ERROR)
        "tornado.access": {"level": "INFO", "handlers": [HANDLER], "propagate": False},
    },
)
# traitlets merges this into its default logging config, whose "console"
# handler the app's own logger (KernelGatewayApp) writes to: give it the same
# formatter and filter
_logging["handlers"]["console"] = {
    "formatter": _logging["handlers"][HANDLER]["formatter"],
    "filters": ["request_context"],
}
c.Application.logging_config = _logging
c.Application.log_level = os.environ.get("MP_APP_LOG_LEVEL", "INFO")
