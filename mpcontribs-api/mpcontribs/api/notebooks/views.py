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
from mongoengine.context_managers import no_dereference

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
    fields = ["id", "nbformat", "nbformat_minor"]
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
    with no_dereference(Contributions) as Contribs:
        # TODO get a random max_docs slice to avoid collisions in parallel Fargate tasks

        # remove dangling and unset missing notebooks
        nbs_total, nbs_count = -1, -1
        ctrbs_cnt = Contribs.objects._cursor.collection.estimated_document_count()
        nbs_cnt = Notebooks.objects._cursor.collection.estimated_document_count()

        if ctrbs_cnt != nbs_cnt:
            contribs = Contribs.objects(notebook__exists=True).only("notebook")
            nids = [contrib.notebook.id for contrib in contribs]
            if len(nids) < nbs_cnt:
                nbs = Notebooks.objects(id__nin=nids).only("id")
                nbs_total = nbs.count()
                max_docs = 2500
                nbs[:max_docs].delete()
                nbs_count = nbs_total if nbs_total < max_docs else max_docs
            else:
                missing_nids = set(nids) - set(Notebooks.objects.distinct("id"))
                if missing_nids:
                    upd_contribs = Contribs.objects(notebook__in=list(missing_nids))
                    nupd_total = upd_contribs.count()
                    nupd = upd_contribs.update(unset__notebook="")
                    print(f"unset notebooks for {nupd}/{nupd_total} contributions")

        # build missing notebooks
        max_docs = NotebooksResource.max_limit
        cids = request.args.get("cids", "").split(",")[:max_docs]

        if cids[0]:
            documents = Contribs.objects(id__in=cids)
        else:
            documents = Contribs.objects(notebook__exists=False)[:max_docs]

        total = documents.count()
        count = 0

        for document in documents:
            if document.notebook is not None:
                # NOTE document.notebook.delete() doesn't trigger pre_delete signal?
                nb = Notebooks.objects.get(id=document.notebook.id)
                nb.delete()

            cells = [
                # define client only once in kernel
                # avoids API calls for regex expansion for query parameters
                nbf.new_code_cell(
                    "\n".join(
                        [
                            "if 'client' not in locals():",
                            "\tclient = Client(",
                            '\t\theaders={"X-Authenticated-Groups": "admin"},',
                            f'\t\thost="{MPCONTRIBS_API_HOST}"',
                            "\t)",
                            "print(client.get_number_contributions())",
                            # return something. See while loop in `run_cells`
                        ]
                    )
                ),
                nbf.new_code_cell("\n".join([
                    f'c = client.get_contribution("{document.id}")',
                    'c.display()'
                ])),
            ]

            if document.tables:
                cells.append(nbf.new_markdown_cell("## Tables"))
                for table in document.tables:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f't = client.get_table("{table.id}")',
                            't.display()'
                        ]))
                    )

            if document.structures:
                cells.append(nbf.new_markdown_cell("## Structures"))
                for structure in document.structures:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f's = client.get_structure("{structure.id}")',
                            's.display()'
                        ]))
                    )

            if document.attachments:
                cells.append(nbf.new_markdown_cell("## Attachments"))
                for attachment in document.attachments:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f'a = client.get_attachment("{attachment.id}")',
                            'a.info()'
                        ]))
                    )

            cid = str(document.id)
            try:
                outputs = execute_cells(cid, cells)
            except Exception as e:
                raise ValueError(f"notebook generation for {cid} failed: {e}")

            if not outputs:
                raise ValueError(f"notebook generation for {cid} failed!")

            for idx, output in outputs.items():
                cells[idx]["outputs"] = output

            doc = deepcopy(seed_nb)
            doc["cells"] += cells[1:]  # skip localhost Client

            document.notebook = Notebooks(**doc).save()
            document.save(signal_kwargs={"skip": True})
            count += 1

        return f"{count}/{total} notebooks built & {nbs_count}/{nbs_total} notebooks deleted"
