# -*- coding: utf-8 -*-
import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest.methods import Fetch
from flask_mongorest import operators as ops
from flask_sse import sse
from flask import Blueprint, request
from copy import deepcopy
from mongoengine import DoesNotExist
from nbformat import v4 as nbf
from enterprise_gateway.client.gateway_client import GatewayClient
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.structures.document import Structures


templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)
client = GatewayClient()
seed_nb = nbf.new_notebook()
seed_nb["cells"] = [
    nbf.new_code_cell(
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


class NotebooksResource(Resource):
    document = Notebooks
    filters = {"is_public": [ops.Boolean]}
    fields = ["is_public", "nbformat", "nbformat_minor", "metadata", "cells"]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch]

    def get(self, **kwargs):
        cid = kwargs["pk"]
        qfilter = lambda qs: self.has_read_permission(request, qs.clone())
        try:
            # trigger DoesNotExist if necessary (due to permissions or non-existence)
            nb = self._resource.get_object(cid, qfilter=qfilter)
            try:
                if not nb.cells[-1]["outputs"]:
                    kernel = client.start_kernel("python3")

                    for idx, cell in enumerate(nb.cells):
                        if cell["cell_type"] == "code":
                            output = kernel.execute(cell["source"])
                            if output:
                                outtype = (
                                    "text/html"
                                    if output.startswith("<div")
                                    else "text/plain"
                                )
                                cell["outputs"].append(
                                    {
                                        "data": {outtype: output},
                                        "metadata": {},
                                        "transient": {},
                                        "output_type": "display_data",
                                    }
                                )
                            sse.publish(
                                {"message": idx + 1}, type="notebook", channel=cid
                            )

                    nb.cells[1] = nbf.new_code_cell(
                        "client = load_client('<your-api-key-here>')"
                    )
                    nb.save()  # calls Notebooks.clean()
                    sse.publish({"message": 0}, type="notebook", channel=cid)
                    client.shutdown_kernel(kernel)
            except Exception as ex:
                print(ex)
                sse.publish({"message": -1}, type="notebook", channel=cid)
            return self._resource.serialize(nb, params=request.args)

        except DoesNotExist:
            nb = None
            try:
                nb = Notebooks.objects.only("pk").get(pk=cid)
            except DoesNotExist:
                # create and save unexecuted notebook, also start entry to avoid rebuild on subsequent requests
                contrib = Contributions.objects.get(id=cid)
                cells = [
                    nbf.new_code_cell(
                        "headers = {'X-Consumer-Groups': 'admin', 'X-Consumer-Username': 'phuck@lbl.gov'}\n"
                        "client = load_client(headers=headers)"
                    ),
                    nbf.new_code_cell(
                        f"contrib = client.contributions.get_entry(pk='{cid}', _fields=['_all']).result()"
                    ),
                    nbf.new_markdown_cell("## Info"),
                    nbf.new_code_cell(
                        "fields = ['title', 'owner', 'authors', 'description', 'urls']\n"
                        "prov = client.projects.get_entry(pk=contrib['project'], _fields=fields).result()\n"
                        "HierarchicalData(prov)"
                    ),
                    nbf.new_markdown_cell("## HData"),
                    nbf.new_code_cell("HierarchicalData(contrib['data'])"),
                ]

                tables = Tables.objects.only("id", "name").filter(contribution=cid)
                if tables:
                    cells.append(nbf.new_markdown_cell("## Tables"))
                    for table in tables:
                        cells.append(nbf.new_markdown_cell(table.name))
                        cells.append(
                            nbf.new_code_cell(
                                f"table = client.tables.get_entry(pk='{table.id}', _fields=['_all']).result()\n"
                                "Table.from_dict(table)"
                            )
                        )
                        cells.append(nbf.new_code_cell("Plot.from_dict(table)"))

                structures = Structures.objects.only("id", "name").filter(
                    contribution=cid
                )
                if structures:
                    cells.append(nbf.new_markdown_cell("## Structures"))
                    for structure in structures:
                        cells.append(nbf.new_markdown_cell(structure.name))
                        cells.append(
                            nbf.new_code_cell(
                                "structure = client.structures.get_entry(\n"
                                f"\tpk='{structure.id}', _fields=['lattice', 'sites', 'charge']\n"
                                ").result()\n"
                                "Structure.from_dict(structure)"
                            )
                        )

                nb = Notebooks(pk=cid, is_public=contrib.is_public)
                doc = deepcopy(seed_nb)
                doc["cells"] += cells
                self.Schema().update(nb, doc)
                nb.save()  # calls Notebooks.clean()
                return self.get(**kwargs)

            if nb is not None:
                raise DoesNotExist(
                    f"Notebook {nb.id} exists but user not in project group"
                )
