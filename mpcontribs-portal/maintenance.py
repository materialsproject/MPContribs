import os
import json

from itertools import combinations
from mpcontribs.portal.views import make_download
from mpcontribs.client import Client

FORMATS = ["json", "csv"]
HEADERS = {"X-Authenticated-Groups": os.environ["ADMIN_GROUP"]}


def generate_downloads(names=None):
    q = {"name__in": names} if names else {}
    client = Client(host=os.environ["MPCONTRIBS_API_HOST"], headers=HEADERS)
    projects = client.projects.queryProjects(
        _fields=["name", "stats"], **q
    ).result().get("data", [])
    skip = {"columns", "contributions"}
    print("PROJECTS", len(projects))

    for project in projects:
        name = project["name"]
        include = [k for k, v in project["stats"].items() if k not in skip and v]

        for fmt in FORMATS:
            query = {"project": name, "format": fmt}
            resp = make_download(client, query, [])
            print(name, json.loads(resp.content))

            if include:
                for r in range(1, len(include)+1):
                    for combo in combinations(include, r):
                        resp = make_download(client, query, combo)
                        print(name, combo, json.loads(resp.content))
