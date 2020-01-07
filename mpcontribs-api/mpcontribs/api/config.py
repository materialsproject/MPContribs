"""configuration module for MPContribs Flask API"""

import os
import datetime

DEBUG = bool(os.environ.get('FLASK_ENV') == 'development')
JSON_SORT_KEYS = False
JSON_ADD_STATUS = False
FLASK_LOG_LEVEL = 'DEBUG'  # if DEBUG else 'WARNING'
SECRET_KEY = 'super-secret'  # TODO in local prod config

USTS_MAX_AGE = 86400
MAIL_DEFAULT_SENDER = 'phuck@lbl.gov'  # TODO environment variable
MAIL_TOPIC = os.environ['AWS_SNS_TOPIC_ARN']

MPCONTRIBS_DB = 'mpcontribs-dev' if DEBUG else 'mpcontribs'
MPCONTRIBS_MONGO_HOST = os.environ.get('MPCONTRIBS_MONGO_HOST', 'localhost')
MONGODB_SETTINGS = {
    'host': f"mongodb+srv://{MPCONTRIBS_MONGO_HOST}/{MPCONTRIBS_DB}?retryWrites=true",
    'connect': False, 'db': MPCONTRIBS_DB
}

SWAGGER = {
    'hide_top_bar': True,
    'doc_expansion': "none",
    'doc_dir': os.path.join(os.path.dirname(__file__), 'swagger'),
    "specs": [{
        "endpoint": 'apispec',
        "route": '/apispec.json',
        "rule_filter": lambda rule: True,  # all in
        "model_filter": lambda tag: True,  # all in
    }],
    "specs_route": "/", "head_text": '\n'.join([
        "<!-- Global site tag (gtag.js) - Google Analytics -->",
        '<script async src= "https://www.googletagmanager.com/gtag/js?id=UA-140392573-3"></script>',
        "<script>",
        "window.dataLayer = window.dataLayer || [];",
        "function gtag(){dataLayer.push(arguments);}",
        "gtag('js', new Date());",
        "gtag('config', 'UA-140392573-3');",
        "</script>"
    ])
}

TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "MPContribs API",
        "description": "Operations to contribute, update and retrieve materials data on Materials Project",
        "termsOfService": "https://materialsproject.org/terms",
        "version": datetime.datetime.today().strftime('%Y.%m.%d'),
        "contact": {
            "name": "MPContribs",
            "email": "phuck@lbl.gov",
            "url": "https://mpcontribs.org",
        },
        "license": {
            "name": "Creative Commons Attribution 4.0 International License",
            "url": "https://creativecommons.org/licenses/by/4.0/"
        }
    },
    'tags': [{
        'name': 'projects', 'description': 'contain provenance information about contributed datasets. Admins can \
        create and delete projects which also deletes all contributions including tables, structures, notebooks \
        and cards for the project. Only users who have been added to a project can update its contents. While \
        unpublished, only users on the project can retrieve its data or view it on the \
        <a href="https://portal.mpcontribs.org">Portal</a>. Making a project public does not automatically publish all \
        its contributions, tables, and structures. These are separately set to public individually or in bulk.'''
    }, {
        'name': 'contributions', 'description': 'contain simple hierarchical data which will show up on the MP details \
        page for MP material(s) - see cards below. Tables (rows and columns) as well as structures can be added to a \
        contribution. Each contribution uses `mp-id` or composition as identifier to associate its data with the \
        according entries on MP. Only admins or users on the project can create, update or delete contributions, and \
        while unpublished, retrieve its data or view it on the <a href="https://portal.mpcontribs.org">Portal</a>. The \
        same permission controls are in place for associated tables, structures, notebooks, and cards. These \
        contribution components are deleted along with a contribution.'
    }, {
        'name': 'tables', 'description': 'are simple spreadsheet-type tables with columns and rows saved as Pandas \
        <a href="https://pandas.pydata.org/pandas-docs/stable/getting_started/dsintro.html#dataframe">DataFrames</a> \
        which can be added to a contribution.'
    }, {
        'name': 'structures', 'description': 'are \
        <a href="https://pymatgen.org/_modules/pymatgen/core/structure.html#Structure">pymatgen structures</a> which \
        can be added to a contribution.'
    }, {
        'name': 'notebooks', 'description': 'are Jupyter \
        <a href="https://jupyter-notebook.readthedocs.io/en/stable/notebook.html#notebook-documents">notebook</a> \
        documents generated and saved on first request for every contribution. They form the basis for Contribution \
        Details Pages on the <a href="https://portal.mpcontribs.org">Portal</a>.'
    }, {
        'name': 'cards', 'description': 'are pre-generated embeddable previews (HTML) for each contribution shown on \
        the MP material details pages.'
    }, {
        'name': 'redox_thermo_csp', 'description': 'is a dedicated endpoint to retrieve data for the \
        <a href="https://portal.mpcontribs.org/redox_thermo_csp/">RedoxThermoCSP</a> landing page.'
    }],
    "securityDefinitions": {
        "ApiKeyAuth": {
            'description': 'MP API key to authorize requests',
            'name': 'X-API-KEY',
            'in': 'header',
            'type': 'apiKey'
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "host": '0.0.0.0:5000' if DEBUG else "api.mpcontribs.org",
    "schemes": ['http', 'https'] if DEBUG else ['https'],
}
