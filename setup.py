# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import io, re, glob, os
from setuptools import setup, find_namespace_packages, find_packages

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name = 'mpcontribs',
    version = '2019.01.31',
    description = "The Materials Project's Community Contribution Framework",
    author = 'Patrick Huck',
    author_email = 'phuck@lbl.gov',
    url = 'https://mpcontribs.org',
    #packages = find_namespace_packages(include=['mpcontribs-*']),
    packages = ['mpcontribs-api.mpcontribs.api',
                'mpcontribs-users.mpcontribs.users'],
    install_requires = required,
    #dependency_links = ['git+https://github.com/rochacbruno/flasgger.git#egg=flasgger-0.9.3.dev0'],
    license = 'MIT',
    keywords = ['materials', 'contribution', 'framework', 'data', 'interactive', 'jupyter'],
    scripts = glob.glob(os.path.join(SETUP_PTH, "scripts", "*")),
)
