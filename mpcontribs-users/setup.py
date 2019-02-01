# -*- coding: utf-8 -*-
import io, re, glob, os
from setuptools import setup

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name = 'mpcontribs-users',
    version = '2019.01.31',
    description = 'Contributor Modules to enable their data submissions via MPContribs',
    author = 'Patrick Huck',
    author_email = 'phuck@lbl.gov',
    url = 'https://mpcontribs.org',
    packages = ['mpcontribs.users'],
    #install_requires = required,
    #dependency_links = ['git+https://github.com/rochacbruno/flasgger.git#egg=flasgger-0.9.3.dev0'],
    license = 'MIT',
    zip_safe=False,
)
