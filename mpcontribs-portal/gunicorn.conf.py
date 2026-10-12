import os

from mp_logging import gunicorn_logconfig_dict

bind = "0.0.0.0:{}".format(os.getenv("PORTAL_PORT"))
worker_class = "gevent"
workers = os.getenv("NWORKERS")
statsd_host = "{}:8125".format(os.getenv("DD_AGENT_HOST"))

# gunicorn's own error and access logs go through the same structured logging
# config as the application (see `mp_logging`). Applied in the master before
# forking; the access log formatter maps gunicorn's atoms to Datadog's
# standard HTTP attributes, so the format string itself is only a fallback.
logconfig_dict = gunicorn_logconfig_dict(
    app_loggers=("mpcontribs",), debug=os.getenv("NODE_ENV") == "development"
)
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(m)s %(U)s %(q)s %(s)s %(B)s %(D)s "%(f)s" "%(a)s"'

max_requests = os.getenv("MAX_REQUESTS")
max_requests_jitter = os.getenv("MAX_REQUESTS_JITTER")
proc_name = os.getenv("SUPERVISOR_PROCESS_NAME")
reload = bool(os.getenv("RELOAD", False))
