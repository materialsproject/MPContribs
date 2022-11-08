# -*- coding: utf-8 -*-
import datetime
from setuptools import setup

setup(
    name="mpcontribs-api",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="API for community-contributed Materials Project data",
    author="Patrick Huck",
    author_email="phuck@lbl.gov",
    url="https://mpcontribs.org",
    packages=["mpcontribs.api"],
    install_requires=[
        "apispec<6",
        "asn1crypto",
        "blinker",
        "boltons",
        "css-html-js-minify",
        "dateparser",
        "ddtrace",
        "dnspython",
        "filetype",
        "flasgger-tschaume>=0.9.7",
        "flask-compress",
        "flask-marshmallow",
        "flask-mongorest-mpcontribs>=3.2.1",
        "Flask-RQ2",
        "gunicorn[gevent]",
        "jinja2",
        "json2html",
        "more-itertools",
        "nbformat",
        "notebook",
        "pint<0.20",
        "psycopg2-binary",
        "pymatgen",
        "pyopenssl",
        "python-snappy",
        "rq-scheduler",
        "semantic-version",
        "supervisor",
        "setproctitle",
        "uncertainties",
        "websocket_client",
        "zstandard",
    ],
    extras_require={
        "dev": ["pytest", "flake8"]
    },
    license="MIT",
    zip_safe=False,
)
