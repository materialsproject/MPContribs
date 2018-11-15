# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import io, re, glob, os
from setuptools import setup

package_name = 'mpcontribs'
init_py = io.open('{}/__init__.py'.format(package_name)).read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", init_py))
metadata['doc'] = re.findall('"""(.+)"""', init_py)[0]
SETUP_PTH = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name = package_name,
    version = metadata['version'],
    description = metadata['doc'],
    author = metadata['author'],
    author_email = metadata['email'],
    url = metadata['url'],
    packages = [
        package_name, '{}.io'.format(package_name), '{}.webui'.format(package_name),
        '{}.explorer'.format(package_name), '{}.portal'.format(package_name),
        '{}.rest'.format(package_name), '{}.builder'.format(package_name),
        '{}.api'.format(package_name),
    ],
    install_requires = required,
    license = 'MIT',
    keywords = ['materials', 'contribution', 'framework', 'data', 'interactive', 'jupyter'],
    scripts = glob.glob(os.path.join(SETUP_PTH, "scripts", "*")),
)
