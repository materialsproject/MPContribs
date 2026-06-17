import os
from jinja2 import Environment, FileSystemLoader

DIR = os.path.abspath(os.path.dirname(__file__))
PRODUCTION = int(os.environ.get("PRODUCTION", "1"))
DEFAULT_NWORKERS = 2 if PRODUCTION else 1
NWORKERS = int(os.environ.get("NWORKERS", DEFAULT_NWORKERS))

deployments = {}

for deployment in os.environ.get("DEPLOYMENTS", "ml:10002").split(","):
    name, s3, tm, portal_port = deployment.split(":")
    api_port = 10000 + int(portal_port) % 8080
    deployments[name] = {
        "api_port": api_port,
        "portal_port": portal_port,
        "s3": s3,
        "tm": tm.upper()
    }

kwargs = {
    "production": PRODUCTION,
    "deployments": deployments,
    "nworkers": NWORKERS,
    "reload": int(not PRODUCTION),
    "node_env": "production" if PRODUCTION else "development",
    "dd_agent_host": "localhost" if PRODUCTION else "datadog",
    "mpcontribs_api_host": "localhost" if PRODUCTION else "contribs-apis",
    "log_level": "INFO" if PRODUCTION else "DEBUG",
}

env = Environment(loader=FileSystemLoader(DIR))
template = env.get_template("supervisord.conf.jinja")
template.stream(**kwargs).dump("supervisord.conf")
