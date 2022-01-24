import os
from jinja2 import Environment, FileSystemLoader

DIR = os.path.abspath(os.path.dirname(__file__))
PRODUCTION = int(os.environ.get("PRODUCTION", "1"))

deployments = {}

for deployment in os.environ.get("DEPLOYMENTS", "ml:5002").split(","):
    name, db, s3, tm, api_port = deployment.split(":")
    portal_port = 8080 + int(api_port) % 5000
    deployments[name] = {
        "api_port": api_port,
        "portal_port": portal_port,
        "db": db,
        "s3": s3,
        "tm": tm.upper()
    }

kwargs = {
    "production": PRODUCTION,
    "deployments": deployments,
    "nworkers": 2 if PRODUCTION else 1,
    "reload": "" if PRODUCTION else "--reload",
    "node_env": "production" if PRODUCTION else "development",
    "flask_log_level": "INFO" if PRODUCTION else "DEBUG",
    "jupyter_gateway_host": "localhost:8888" if PRODUCTION else "kernel-gateway:8888",
    "dd_agent_host": "localhost" if PRODUCTION else "datadog",
    "mpcontribs_api_host": "localhost" if PRODUCTION else "contribs-apis",
}
kwargs["flask_env"] = kwargs["node_env"]
kwargs["jupyter_gateway_url"] = "http://" + kwargs["jupyter_gateway_host"]

env = Environment(loader=FileSystemLoader(DIR))
template = env.get_template("supervisord.conf.jinja")
template.stream(**kwargs).dump("supervisord.conf")
