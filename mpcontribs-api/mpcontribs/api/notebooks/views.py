import os
import requests
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest.methods import Fetch
from flask_mongorest import operators as ops
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


class CustomGatewayClient(GatewayClient):

    def start_kernel(self):
        json_data = {'name': 'python3', 'env': {
            'KERNEL_GATEWAY_HOST': self.DEFAULT_GATEWAY_HOST
        }}
        response = requests.post(self.http_api_endpoint, data=json_encode(json_data))

        if response.status_code == 201:
            json_data = response.json()
            kernel_id = json_data.get("id")
            self.log.info('Started kernel with id {}'.format(kernel_id))
        else:
            raise RuntimeError('Error starting kernel : {} response code \n {}'.
                               format(response.status_code, response.content))

        return CustomKernelClient(self.http_api_endpoint, self.ws_api_endpoint, kernel_id, logger=self.log)


class CustomKernelClient(KernelClient):

    def execute(self, code):
        response = []
        try:
            msg_id = self._send_request(code)
            post_idle = False
            while True:
                msg = self._get_response(msg_id, 60, post_idle)
                if msg:
                    msg_type, content = msg['msg_type'], msg['content']
                    if msg_type == 'error' or (msg_type == 'execute_reply' and content['status'] == 'error'):
                        self.log.error(f"{content['ename']}:{content['evalue']}:{content['traceback']}")
                    elif msg_type == 'execute_result' or msg_type == 'display_data':
                        content['output_type'] = msg_type
                        response.append(content)
                    elif msg_type == 'status':
                        if content['execution_state'] == 'idle':
                            post_idle = True
                            continue
                    else:
                        self.log.debug(f"Unhandled response for msg_id: {msg_id} of msg_type: {msg_type}")
                elif msg is None:  # We timed out. If post idle, its ok, else make mention of it
                    if not post_idle:
                        self.log.warning(f"Unexpected timeout occurred for {msg_id} - no 'idle' status received!")
                    break
        except BaseException as b:
            self.log.debug(b)

        return response


client = CustomGatewayClient()
with open('kernel_imports.ipynb') as fh:
    seed_nb = read(fh, 4)


class NotebooksResource(Resource):
    document = Notebooks
    filters = {
        'project': [ops.In, ops.Exact],
        'is_public': [ops.Boolean]
    }
    fields = [
        'id', 'project', 'is_public', 'nbformat',
        'nbformat_minor', 'metadata', 'cells'
    ]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch]

    def get(self, **kwargs):
        cid = kwargs['pk']
        try:
            ret = super().get(**kwargs)
            # nb.restore() ???
        except DoesNotExist:
            nb = None
            try:
                nb = Notebooks.objects.only('id').get(id=cid)
            except DoesNotExist:
                # save empty notebook, also start entry to avoid rebuild on subsequent requests
                print('create empty notebook ...')
                contrib = Contributions.objects.only('project', 'is_public').get(id=cid)
                nb = Notebooks(
                    id=cid,  # to link to the according contribution
                    project=contrib.project.id, is_public=contrib.is_public
                )
                nb.save()  # calls Notebooks.clean()
                return self.get(**kwargs)

            if nb is not None:
                raise DoesNotExist(f'Notebook {nb.id} exists but user not in project group')

        if not ret["cells"]:
            # generate notebook content
            print('generating notebook ...')
            contrib = Contributions.objects.get(id=cid)
            cells = [
                nbf.new_code_cell(
                    "client = load_client() # provide apikey as argument to use api.mpcontribs.org\n"
                    f"contrib = client.contributions.get_entry(pk='{cid}', _fields=['_all']).response().result"
                ),
                nbf.new_markdown_cell("## Provenance Info"),
                nbf.new_code_cell(
                    "prov = client.projects.get_entry(pk=contrib['project'], _fields=['_all']).response().result\n"
                    "RecursiveDict(prov)"
                ),
                nbf.new_markdown_cell(
                    f"## Hierarchical Data for {contrib['identifier']}"
                ),
                nbf.new_code_cell(
                    "HierarchicalData(contrib['data'])"
                )
            ]

            tables = [t.id for t in Tables.objects.only('id').filter(contribution=cid)]
            if tables:
                cells.append(nbf.new_markdown_cell(
                    f"## Tabular Data for {contrib['identifier']}"
                ))
                for ref in tables:
                    cells.append(nbf.new_code_cell(
                        f"table = client.tables.get_entry(pk='{ref}', _fields=['_all']).response().result # DataFrame\n"
                        "Table.from_dict(table)"
                    ))
                    cells.append(nbf.new_code_cell(
                        "Plot.from_dict(table)"
                    ))

            structures = [s.id for s in Structures.objects.only('id').filter(contribution=cid)]
            if structures:
                cells.append(nbf.new_markdown_cell(
                    f"## Pymatgen Structures for {contrib['identifier']}"
                ))
                for ref in structures:
                    cells.append(nbf.new_code_cell(
                        f"structure = client.structures.get_entry(pk='{ref}', _fields=['_all']).response().result\n"
                        f"Structure.from_dict(structure)"
                    ))

            kernel = client.start_kernel()
            for cell in cells:
                if cell.cell_type == 'code':
                    cell['outputs'] = kernel.execute(cell.source)
            client.shutdown_kernel(kernel)

            doc = deepcopy(seed_nb)
            doc['cells'] += cells
            nb = Notebooks.objects.get(id=cid)
            self.Schema().update(nb, doc)
            nb.save()  # calls Notebooks.clean()
            return self.get(**kwargs)

        return ret
