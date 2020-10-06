# -*- coding: utf-8 -*-
import os
import flask_mongorest

from time import sleep
from copy import deepcopy
from nbformat import v4 as nbf
from flask import Blueprint, request, current_app
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch
from flask_mongorest.resources import Resource

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.notebooks import run_cells

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)

MPCONTRIBS_API_HOST = os.environ.get("MPCONTRIBS_API_HOST", "localhost:5000")
seed_nb = nbf.new_notebook()
seed_nb["cells"] = [
    nbf.new_code_cell("from mpcontribs.client import Client"),
    nbf.new_code_cell("client = Client()"),
]


class NotebooksResource(Resource):
    document = Notebooks
    filters = {"id": [ops.In, ops.Exact]}
    fields = ["id"]
    allowed_ordering = ["name"]
    paginate = True
    default_limit = 10
    max_limit = 100

    @staticmethod
    def get_optional_fields():
        return ["nbformat", "nbformat_minor", "metadata", "cells"]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch, BulkFetch]


def execute_cells(cid, cells):
    ntries = 0
    while ntries < 5:
        for kernel_id, running_cid in current_app.kernels.items():
            if running_cid is None:
                current_app.kernels[kernel_id] = cid
                outputs = run_cells(kernel_id, cid, cells)
                current_app.kernels[kernel_id] = None
                return outputs
            else:
                print(f"{kernel_id} busy with {running_cid}")
        else:
            print("WAITING for a kernel to become available")
            sleep(5)
            ntries += 1


@notebooks.route("/build")
def build():
    # TODO clean up dangling notebooks?
    max_docs = NotebooksResource.max_limit
    cids = request.args.get("cids", "").split(",")[:max_docs]

    if cids[0]:
        documents = Contributions.objects(id__in=cids)
    else:
        documents = Contributions.objects(notebook__exists=False)[:max_docs]

    total = documents.count()
    count = 0

    for document in documents:
        if document.notebook is not None:
            document.notebook.delete()

        cells = [
            # define client only once in kernel
            # avoids API calls for regex expansion for query parameters
            nbf.new_code_cell(
                "\n".join(
                    [
                        "if 'client' not in locals():",
                        "\tclient = Client(",
                        '\t\theaders={"X-Consumer-Groups": "admin"},',
                        f'\t\thost="{MPCONTRIBS_API_HOST}"',
                        "\t)",
                    ]
                )
            ),
            nbf.new_code_cell(f'client.get_contribution("{document.id}").pretty()'),
        ]

        if document.tables:
            cells.append(nbf.new_markdown_cell("## Tables"))
            for table in document.tables:
                cells.append(
                    nbf.new_code_cell(f'client.get_table("{table.id}").plot()')
                )

        if document.structures:
            cells.append(nbf.new_markdown_cell("## Structures"))
            for structure in document.structures:
                cells.append(
                    nbf.new_code_cell(f'client.get_structure("{structure.id}")')
                )

        cid = str(document.id)
        outputs = execute_cells(cid, cells)
        if not outputs:
            raise ValueError(f"notebook generation for {cid} failed!")

        for idx, output in outputs.items():
            cells[idx]["outputs"] = output

        doc = deepcopy(seed_nb)
        doc["cells"] += cells[1:]  # skip localhost Client

        document.notebook = Notebooks(**doc).save()
        document.save(signal_kwargs={"skip": True})
        count += 1

    return f"{count}/{total} notebooks built"
