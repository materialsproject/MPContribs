import io, re, glob, os
from setuptools import setup

package_name = 'mpcontribs'
init_py = io.open('{}/__init__.py'.format(package_name)).read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", init_py))
metadata['doc'] = re.findall('"""(.+)"""', init_py)[0]
SETUP_PTH = os.path.dirname(os.path.abspath(__file__))

setup(
    name = package_name,
    version = metadata['version'],
    description = metadata['doc'],
    author = metadata['author'],
    author_email = metadata['email'],
    url = metadata['url'],
    packages = [
        package_name, '{}.fake'.format(package_name),
        '{}.io'.format(package_name), '{}.webui'.format(package_name),
        '{}.explorer'.format(package_name), '{}.pmg_utils'.format(package_name),
        '{}.rest'.format(package_name),
    ],
    install_requires = [
        'numpy', 'scipy', 'Flask', 'pandas', 'plotly', 'six', 'monty',
        'matplotlib', 'pymongo', 'pyyaml', 'ipython', 'cufflinks',
        'Django>=1.8.5,<1.9', 'archieml', 'django-browserid', 'sphinx', 'notebook',
        'ipywidgets', 'celery', 'tqdm', 'beautifulsoup4', 'whichcraft',
        'unidecode', 'psutil', 'nbformat', 'xlrd', 'django-nopassword'
    ],
    license = 'MIT',
    keywords = ['materials', 'contribution', 'framework', 'data', 'interactive'],
    scripts = glob.glob(os.path.join(SETUP_PTH, "scripts", "*")),
)
