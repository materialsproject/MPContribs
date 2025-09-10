import ddtrace.auto  # noqa: F401
import os

bind = "0.0.0.0:{}".format(os.getenv("API_PORT"))
worker_class = "gevent"
workers = os.getenv("NWORKERS")
statsd_host = "{}:8125".format(os.getenv("DD_AGENT_HOST"))
accesslog = "-"
errorlog = "-"
access_log_format = '{}/{}: %(h)s %(t)s %(m)s %(U)s?%(q)s %(H)s %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s %({{x-consumer-id}}i)s'.format(
    os.getenv("SUPERVISOR_GROUP_NAME"), os.getenv("SUPERVISOR_PROCESS_NAME")
)
max_requests = os.getenv("MAX_REQUESTS")
max_requests_jitter = os.getenv("MAX_REQUESTS_JITTER")
proc_name = os.getenv("SUPERVISOR_PROCESS_NAME")
reload = bool(os.getenv("RELOAD", False))
