# -*- coding: utf-8 -*-
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb["cells"] = [
    nbf.v4.new_code_cell(
        "\n".join(
            [
                "from mpcontribs.client import load_client",
                "from mpcontribs.io.core.components.hdata import HierarchicalData",
                "from mpcontribs.io.core.components.tdata import Table # DataFrame with Backgrid IPython Display",
                "from mpcontribs.io.core.components.gdata import Plot # Plotly interactive graph",
                "from pymatgen import Structure",
            ]
        )
    )
]

nbf.write(nb, "kernel_imports.ipynb")
