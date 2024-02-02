# -*- coding: utf-8 -*-
from setuptools import setup


def local_version(version):
    # https://github.com/pypa/setuptools_scm/issues/342
    return ""


with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="mpcontribs-client",
    python_requires=">=3.8",
    author="Patrick Huck",
    author_email="phuck@lbl.gov",
    description="client library for MPContribs API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/MPContribs/tree/master/mpcontribs-client",
    packages=["mpcontribs.client"],
    install_requires=[
        "boltons",
        "bravado",
        "filetype",
        "flatten-dict",
        "ipython",
        "json2html",
        "pandas",
        "pint<0.20",
        "plotly",
        "pyIsEmail",
        "pymatgen",
        "pymongo",
        "requests-futures",
        "swagger-spec-validator",
        "tqdm",
        "ujson",
        "semantic-version",
        "cachetools",
    ],
    extras_require={
        "dev": [
            "flake8",
            "pytest",
            "pytest-flake8",
            "pytest-pycodestyle",
            "pytest-cov",
            "py",
        ]
    },
    license="MIT",
    zip_safe=False,
    include_package_data=True,
    use_scm_version={
        "root": "..",
        "relative_to": __file__,
        "local_scheme": local_version,
    },
    setup_requires=["setuptools_scm"],
)
