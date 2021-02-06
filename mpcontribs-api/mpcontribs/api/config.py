# -*- coding: utf-8 -*-
"""configuration module for MPContribs Flask API"""

import os
import datetime
import json
import gzip

formulae_path = os.path.join(
    os.path.dirname(__file__), "contributions", "formulae.json.gz"
)

with gzip.open(formulae_path) as f:
    FORMULAE = json.load(f)

API_CNAME = os.environ.get("API_CNAME")
DEBUG = bool(API_CNAME.startswith("localhost"))
PORTAL_CNAME = os.environ.get("PORTAL_CNAME")
JSON_SORT_KEYS = False
JSON_ADD_STATUS = False
FLASK_LOG_LEVEL = "DEBUG" if DEBUG else "WARNING"
SECRET_KEY = "super-secret"  # TODO in local prod config
SCHEMES = ["http"] if DEBUG else ["https"]

USTS_MAX_AGE = 2.628e6  # 1 month
MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
MAIL_TOPIC = os.environ.get("AWS_SNS_TOPIC_ARN")

MPCONTRIBS_DB = os.environ.get("MPCONTRIBS_DB_NAME", "mpcontribs")
MPCONTRIBS_MONGO_HOST = os.environ.get("MPCONTRIBS_MONGO_HOST")
MONGODB_SETTINGS = {
    # Changed in version 3.9: retryWrites now defaults to True.
    "host": f"mongodb+srv://{MPCONTRIBS_MONGO_HOST}/{MPCONTRIBS_DB}",
    "connect": False,
    "db": MPCONTRIBS_DB,
    "compressors": ["snappy", "zstd", "zlib"],
}
REDIS_URL = "redis://" + os.environ.get("REDIS_ADDRESS", "redis")

SWAGGER = {
    "swagger_ui_bundle_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js",
    "swagger_ui_standalone_preset_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js",
    "jquery_js": "//unpkg.com/jquery@2.2.4/dist/jquery.min.js",
    "swagger_ui_css": "//unpkg.com/swagger-ui-dist@3/swagger-ui.css",
    "uiversion": 3,
    "hide_top_bar": True,
    "doc_expansion": "none",
    "doc_dir": os.path.join(os.path.dirname(__file__), "swagger"),
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "specs_route": "/",
}

TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": API_CNAME.rsplit(".", 2)[0].replace("-", " ").upper(),
        "description": "Operations to contribute, update and retrieve materials data on Materials Project",
        "termsOfService": "https://materialsproject.org/terms",
        "version": datetime.datetime.today().strftime("%Y.%m.%d"),
        "contact": {
            "name": "MPContribs",
            "email": "contribs@materialsproject.org",
            "url": "https://mpcontribs.org",
        },
        "license": {
            "name": "Creative Commons Attribution 4.0 International License",
            "url": "https://creativecommons.org/licenses/by/4.0/",
        },
    },
    "tags": [
        {
            "name": "projects",
            "description": f'contain provenance information about contributed datasets. Apply for a project \
        <a href="https://contribs.materialsproject.org/#apply">here</a> to get started. \
        Deleting projects will also delete all contributions including tables, structures, notebooks \
        and cards for the project. Only users who have been added to a project can update its contents. While \
        unpublished, only users on the project can retrieve its data or view it on the \
        <a href="{SCHEMES[0]}://{PORTAL_CNAME}">Portal</a>. Making a project public does not automatically publish all \
        its contributions, tables, and structures. These are separately set to public individually or in bulk.'
            "",
        },
        {
            "name": "contributions",
            "description": f'contain simple hierarchical data which will show up as cards on the MP details \
        page for MP material(s). Tables (rows and columns) as well as structures can be added to a \
        contribution. Each contribution uses `mp-id` or composition as identifier to associate its data with the \
        according entries on MP. Only admins or users on the project can create, update or delete contributions, and \
        while unpublished, retrieve its data or view it on the <a href="{SCHEMES[0]}://{PORTAL_CNAME}">Portal</a>. \
        Contribution components (tables and structures) are deleted along with a contribution.',
        },
        {
            "name": "tables",
            "description": 'are simple spreadsheet-type tables with columns and rows saved as Pandas \
        <a href="https://pandas.pydata.org/pandas-docs/stable/getting_started/dsintro.html#dataframe">DataFrames</a> \
        which can be added to a contribution.',
        },
        {
            "name": "structures",
            "description": 'are \
        <a href="https://pymatgen.org/_modules/pymatgen/core/structure.html#Structure">pymatgen structures</a> which \
        can be added to a contribution.',
        },
        {
            "name": "notebooks",
            "description": f'are Jupyter \
        <a href="https://jupyter-notebook.readthedocs.io/en/stable/notebook.html#notebook-documents">notebook</a> \
        documents generated and saved when a contribution is saved. They form the basis for Contribution \
        Details Pages on the <a href="[SCHEMES[0]]://{PORTAL_CNAME}">Portal</a>.',
        },
    ],
    "securityDefinitions": {
        "ApiKeyAuth": {
            "description": "MP API key to authorize requests",
            "name": "X-API-KEY",
            "in": "header",
            "type": "apiKey",
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "host": API_CNAME,
    "schemes": SCHEMES,
}


# TODO only load redox_thermo_csp for main deployment
# TEMPLATE["tags"].append(
#     {
#         "name": "redox_thermo_csp",
#         "description": f'is a dedicated endpoint to retrieve data for the \
#     <a href="{SCHEMES[0]}://{PORTAL_CNAME}/redox_thermo_csp/">RedoxThermoCSP</a> landing page.',
#     }
# )
