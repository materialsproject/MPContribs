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
        '{}.io'.format(package_name),
        '{}.webui'.format(package_name)
    ],
    include_package_data=True,
    install_requires = [
        'numpy==1.9.2', 'Flask==0.10.1', 'pandas==0.16.2', 'plotly==1.7.7',
        'six==1.9.0', 'monty==0.6.5', 'matplotlib==1.4.3', 'pymongo==3.0.3',
        'pyyaml==3.11', 'ipython==3.2.1', 'cufflinks==0.4', #'pymatgen-0.0'
    ],
    #setup_requires = [ 'numpy==1.9.1', 'pymatgen-0.0' ],
    #dependency_links = [
    #    'http://github.com/tschaume/pymatgen/tarball/submit_mpfile#egg=pymatgen-0.0'
    #],
    license = 'MIT',
    keywords = ['materials', 'contribution', 'framework', 'data', 'interactive'],
    scripts = glob.glob(os.path.join(SETUP_PTH, "scripts", "*")),
)
