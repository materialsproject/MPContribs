# -*- coding: utf-8 -*-
"""configuration module for MPContribs Flask API"""

import os
import json
import gzip

from mpcontribs.api import __version__

formulae_path = os.path.join(
    os.path.dirname(__file__), "contributions", "formulae.json.gz"
)

with gzip.open(formulae_path) as f:
    FORMULAE = json.load(f)

JSON_ADD_STATUS = False
SECRET_KEY = "super-secret"  # TODO in local prod config

MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
MPCONTRIBS_DB = os.environ.get("MPCONTRIBS_DB_NAME", "mpcontribs")
MPCONTRIBS_MONGO_HOST = os.environ.get("MPCONTRIBS_MONGO_HOST")
MPCONTRIBS_API_HOST = os.environ.get("MPCONTRIBS_API_HOST")
MONGODB_SETTINGS = {
    # Changed in version 3.9: retryWrites now defaults to True.
    "host": f"mongodb+srv://{MPCONTRIBS_MONGO_HOST}/{MPCONTRIBS_DB}",
    "connect": False,
    "db": MPCONTRIBS_DB,
    "compressors": ["snappy", "zstd", "zlib"],
}
REDIS_ADDRESS = os.environ.get("REDIS_ADDRESS", "redis")
REDIS_URL = RQ_REDIS_URL = RQ_DASHBOARD_REDIS_URL = f"redis://{REDIS_ADDRESS}"
DOC_DIR = os.path.join(os.path.dirname(__file__), f"swagger-{MPCONTRIBS_DB}")

SWAGGER = {
    "swagger_ui_bundle_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js",
    "swagger_ui_standalone_preset_js": "//unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js",
    "jquery_js": "//unpkg.com/jquery@2.2.4/dist/jquery.min.js",
    "swagger_ui_css": "//unpkg.com/swagger-ui-dist@3/swagger-ui.css",
    "uiversion": 3,
    "hide_top_bar": True,
    "doc_expansion": "none",
    "doc_dir": DOC_DIR,
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
        "title": "MPContribs API",
        "description": "Operations to contribute, update and retrieve materials data on Materials Project",
        "termsOfService": "https://materialsproject.org/terms",
        "version": __version__,
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
            "description": f'contain provenance information about contributed datasets. \
        Deleting projects will also delete all contributions including tables, structures, attachments, notebooks \
        and cards for the project. Only users who have been added to a project can update its contents. While \
        unpublished, only users on the project can retrieve its data or view it on the \
        Portal. Making a project public does not automatically publish all \
        its contributions, tables, attachments, and structures. These are separately set to public individually or in bulk.'
            "",
        },
        {
            "name": "contributions",
            "description": f'contain simple hierarchical data which will show up as cards on the MP details \
        page for MP material(s). Tables (rows and columns), structures, and attachments can be added to a \
        contribution. Each contribution uses `mp-id` or composition as identifier to associate its data with the \
        according entries on MP. Only admins or users on the project can create, update or delete contributions, and \
        while unpublished, retrieve its data or view it on the Portal. \
        Contribution components (tables,  structures, and attachments) are deleted along with a contribution.',
        },
        {
            "name": "structures",
            "description": 'are \
        <a href="https://pymatgen.org/_modules/pymatgen/core/structure.html#Structure">pymatgen structures</a> which \
        can be added to a contribution.',
        },
        {
            "name": "tables",
            "description": 'are simple spreadsheet-type tables with columns and rows saved as Pandas \
        <a href="https://pandas.pydata.org/pandas-docs/stable/getting_started/dsintro.html#dataframe">DataFrames</a> \
        which can be added to a contribution.',
        },
        {
            "name": "attachments",
            "description": 'are files saved as objects in AWS S3 and not accessible for querying (only retrieval) \
            which can be added to a contribution.',
        },
        {
            "name": "notebooks",
            "description": f'are Jupyter \
        <a href="https://jupyter-notebook.readthedocs.io/en/stable/notebook.html#notebook-documents">notebook</a> \
        documents generated and saved when a contribution is saved. They form the basis for Contribution \
        Details Pages on the Portal.',
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
}
