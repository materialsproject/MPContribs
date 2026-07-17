# -*- coding: utf-8 -*-
import ddtrace.auto
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3"}
nb.cells = [nbf.v4.new_code_cell("from mpcontribs.client import Client")]
nbf.write(nb, "kernel_imports.ipynb")
