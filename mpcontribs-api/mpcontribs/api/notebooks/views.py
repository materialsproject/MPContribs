import os
import requests
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest.methods import Fetch
from flask_mongorest import operators as ops
from flask_sse import sse
from flask import Blueprint
from copy import deepcopy
from mongoengine import DoesNotExist
from nbformat import v4 as nbf
from nbformat import read
from enterprise_gateway.client.gateway_client import GatewayClient, KernelClient
from tornado.escape import json_encode
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.structures.document import Structures

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
notebooks = Blueprint("notebooks", __name__, template_folder=templates)
client = GatewayClient()
with open('kernel_imports.ipynb') as fh:
    seed_nb = read(fh, 4)


class NotebooksResource(Resource):
    document = Notebooks
    filters = {'is_public': [ops.Boolean]}
    fields = ['is_public', 'nbformat', 'nbformat_minor', 'metadata', 'cells']


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch]

    def get(self, **kwargs):
        cid = kwargs['pk']
        try:
            super().get(**kwargs)  # trigger DoesNotExist if necessary
            nb = Notebooks.objects.get(pk=cid)
            if not nb.cells[-1]['outputs']:
                kernel = client.start_kernel('python3')
                for idx, cell in enumerate(nb.cells):
                    if cell['cell_type'] == 'code':
                        cell['outputs'] = kernel.execute(cell['source'])
                        sse.publish({"message": idx+1}, type='notebook', channel=cid)
                else:
                    nb.cells[1] = nbf.new_code_cell("client = load_client('<your-api-key-here>')")
                    try:
                        nb.save()  # calls Notebooks.clean()
                    except Exception as ex:
                        print(ex)
                        sse.publish({"message": -1}, type='notebook', channel=cid)
                    finally:
                        sse.publish({"message": 0}, type='notebook', channel=cid)
                client.shutdown_kernel(kernel)
            return super().get(**kwargs)

        except DoesNotExist:
            nb = None
            try:
                nb = Notebooks.objects.only('pk').get(pk=cid)
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
                    nbf.new_code_cell(
                        "HierarchicalData(contrib['data'])"
                    )
                ]

                tables = [t.id for t in Tables.objects.only('id').filter(contribution=cid)]
                if tables:
                    cells.append(nbf.new_markdown_cell("## Tables"))
                    for ref in tables:
                        cells.append(nbf.new_code_cell(
                            f"table = client.tables.get_entry(pk='{ref}', _fields=['_all']).result()\n"
                            "Table.from_dict(table)"
                        ))
                        cells.append(nbf.new_code_cell(
                            "Plot.from_dict(table)"
                        ))

                structures = [s.id for s in Structures.objects.only('id').filter(contribution=cid)]
                if structures:
                    cells.append(nbf.new_markdown_cell("## Structures"))
                    for ref in structures:
                        cells.append(nbf.new_code_cell(
                            f"structure = client.structures.get_entry(pk='{ref}', _fields=['_all']).result()\n"
                            f"Structure.from_dict(structure)"
                        ))

                nb = Notebooks(pk=cid, is_public=contrib.is_public)
                doc = deepcopy(seed_nb)
                doc['cells'] += cells
                self.Schema().update(nb, doc)
                nb.save()  # calls Notebooks.clean()
                return super().get(**kwargs)

            if nb is not None:
                raise DoesNotExist(f'Notebook {nb.id} exists but user not in project group')
