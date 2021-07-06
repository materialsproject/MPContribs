# -*- coding: utf-8 -*-
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3"}
nb.cells = [
    nbf.v4.new_code_cell(
        "\n".join(
            [
                "import os",
                "import plotly.io as pio",
                "import pandas as pd",
                "from mpcontribs.client import Client",
                "from pymatgen.core import Structure",
                'pio.templates.default = "simple_white"',
            ]
        )
    )
]

nbf.write(nb, "kernel_imports.ipynb")
