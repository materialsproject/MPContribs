# -*- coding: utf-8 -*-
import datetime
from setuptools import setup

setup(
    name="mpcontribs-portal",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="MPContribs Portal",
    author="Patrick Huck",
    author_email="phuck@lbl.gov",
    url="https://docs.mpcontribs.org",
    packages=["mpcontribs.portal", "mpcontribs.users"],
    install_requires=[
        "boltons",
        "boto3",
        "ddtrace",
        "Django>=3.2,<4.0",
        "django-extensions",
        "django-settings-file",
        "django-webpack4-loader",
        "fastnumbers",
        "gunicorn[gevent]",
        "ipykernel",
        "ipython-genutils",
        "jinja2",
        "json2html",
        "monty",
        "mpcontribs-client",
        "nbconvert",
        "nbformat",
        "redis",
        "scipy",
        "setproctitle",
        "whitenoise",
        "pymongo<4.9.1",
    ],
    extras_require={
        "dev": ["pytest", "flake8"]
    },
    license="MIT",
    zip_safe=False,
    include_package_data=True,
)
