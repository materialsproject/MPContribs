# -*- coding: utf-8 -*-
import io, re, glob, os
from setuptools import setup

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name = 'mpcontribs-webtzite',
    version = '2019.01.31',
    description = "Django app containing the core functionality of MP's web site to enable development of pluggable web apps",
    author = 'Patrick Huck',
    author_email = 'phuck@lbl.gov',
    url = 'https://mpcontribs.org',
    packages = ['webtzite'],
    #install_requires = required,
    license = 'MIT',
    zip_safe=False,
)
