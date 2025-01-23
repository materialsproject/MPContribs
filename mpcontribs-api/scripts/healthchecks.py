import os
import sys
import requests

for deployment in os.environ.get("DEPLOYMENTS", "ml:10002").split(","):
    name, _, _, _, _, port = deployment.split(":")
    response = requests.get(f"http://localhost:{port}/healthcheck")
    if response.status_code != 200:
        sys.exit(1)
