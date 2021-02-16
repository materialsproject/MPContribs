# -*- coding: utf-8 -*-
import os
import datetime
from setuptools import setup

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, "requirements.txt")) as f:
    required = f.read().splitlines()

setup(
    name="mpcontribs-api",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="API for community-contributed Materials Project data",
    author="Patrick Huck",
    author_email="phuck@lbl.gov",
    url="https://docs.mpcontribs.org",
    packages=["mpcontribs.api"],
    install_requires=required,
    license="MIT",
    zip_safe=False,
)
