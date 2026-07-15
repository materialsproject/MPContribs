import os

from jinja2 import Environment, FileSystemLoader

DIR = os.path.abspath(os.path.dirname(__file__))
PRODUCTION = int(os.environ.get("PRODUCTION", "1"))
# uvicorn worker count per API process. Same default in dev and prod; override via the NWORKERS env var.
NWORKERS = int(os.environ.get("NWORKERS", "2"))

deployments = {}

# DEPLOYMENTS entries are "name:db:s3:tm:max_projects:api_port" — the format is an external
# deployment contract (also parsed by scripts/healthchecks.py). Only name, db, and api_port are
# consumed today; s3/tm/max_projects are Flask/portal-era fields kept for format compatibility.
for deployment in os.environ.get("DEPLOYMENTS", "ml:ml:ml:MP:3:10002").split(","):
    name, db, _s3, _tm, _max_projects, api_port = deployment.split(":")
    deployments[name] = {
        "api_port": api_port,
        "db": db,
    }

kwargs = {
    "production": PRODUCTION,
    # MPCONTRIBS_ENVIRONMENT drives the new pydantic Settings (log format, debug mode).
    "environment": "prod" if PRODUCTION else "dev",
    # MPCONTRIBS_VERSION is required by Settings; sourced from the image build arg at container start.
    "version": os.environ.get("CONTRIBS_VERSION", os.environ.get("MPCONTRIBS_VERSION", "0.0.0")),
    "deployments": deployments,
    # Consumed by scripts/start.sh: both dev and prod run `uvicorn --workers $NWORKERS`.
    "nworkers": NWORKERS,
    # OTLP/gRPC receiver: the Datadog Agent sidecar in prod, the "datadog" compose service in dev.
    "otel_endpoint": "localhost:4317" if PRODUCTION else "datadog:4317",
}

env = Environment(loader=FileSystemLoader(DIR))
template = env.get_template("supervisord.conf.jinja")
template.stream(**kwargs).dump("supervisord.conf")
