import os
from jinja2 import Environment, FileSystemLoader

DIR = os.path.abspath(os.path.dirname(__file__))
PRODUCTION = int(os.environ.get("PRODUCTION", "1"))
DEFAULT_NWORKERS = 2 if PRODUCTION else 1
NWORKERS = int(os.environ.get("NWORKERS", DEFAULT_NWORKERS))
KG_PORT = 10100

deployments = {}

for deployment in os.environ.get("DEPLOYMENTS", "ml:10002").split(","):
    name, db, s3, tm, max_projects, api_port = deployment.split(":")
    portal_port = 8080 + int(api_port) % 10000
    deployments[name] = {
        "api_port": api_port,
        "portal_port": portal_port,
        "db": db,
        "s3": s3,
        "tm": tm.upper(),
        "max_projects": max_projects if max_projects else 3
    }

kwargs = {
    "production": PRODUCTION,
    "deployments": deployments,
    "nworkers": NWORKERS,
    "reload": int(not PRODUCTION),
    "node_env": "production" if PRODUCTION else "development",
    "flask_log_level": "INFO" if PRODUCTION else "DEBUG",
    "jupyter_gateway_host": f"localhost:{KG_PORT}" if PRODUCTION else f"kernel-gateway:{KG_PORT}",
    "dd_agent_host": "localhost" if PRODUCTION else "datadog",
    "mpcontribs_api_host": "localhost" if PRODUCTION else "contribs-apis",
}
kwargs["flask_debug"] = kwargs["node_env"] == "development"
kwargs["jupyter_gateway_url"] = "http://" + kwargs["jupyter_gateway_host"]

env = Environment(loader=FileSystemLoader(DIR))
template = env.get_template("supervisord.conf.jinja")
template.stream(**kwargs).dump("supervisord.conf")
