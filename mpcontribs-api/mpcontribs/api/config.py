"""configuration module for MPContribs Flask API"""

import os
import datetime

PER_PAGE_MAX = 20
DEBUG = bool(os.environ.get('FLASK_ENV') == 'development')
JSON_SORT_KEYS = False
JSON_ADD_STATUS = False
FLASK_LOG_LEVEL = 'DEBUG' if DEBUG else 'WARNING'
SECRET_KEY = b'super-secret'  # reset in local prod config
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
        "description": "Operations to retrieve materials data contributed to Materials Project",
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
