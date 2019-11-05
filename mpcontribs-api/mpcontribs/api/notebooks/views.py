import requests
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

notebooks = Blueprint("notebooks", __name__)


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


class NotebookView(SwaggerView):

    def get(self, cid):
        """Retrieve (and build) notebook for a single contribution [internal].
        ---
        operationId: get_entry
        parameters:
            - name: cid
              in: path
              type: string
              pattern: '^[a-f0-9]{24}$'
              required: true
              description: contribution ID (ObjectId)
        responses:
            200:
                description: single notebook
                schema:
                    $ref: '#/definitions/NotebooksSchema'
        """
        try:
            nb = Notebooks.objects.get(id=cid)
            nb.restore()
        except DoesNotExist:
            nb = Notebooks()  # start entry to avoid rebuild on subsequent requests
            nb.id = cid  # to link to the according contribution
            nb.save()  # calls Notebooks.clean()
            contrib = Contributions.objects.no_dereference().get(id=cid)
            cells = [
                nbf.new_code_cell(
                    "client = load_client() # provide apikey as argument to use api.mpcontribs.org\n"
                    f"contrib = client.contributions.get_entry(cid='{cid}').response().result"
                ),
                nbf.new_markdown_cell("## Provenance Info"),
                nbf.new_code_cell(
                    "mask = ['title', 'authors', 'description', 'urls', 'other', 'project']\n"
                    "prov = client.projects.get_entry(project=contrib['project'], mask=mask).response().result\n"
                    "RecursiveDict(prov)"
                ),
                nbf.new_markdown_cell(
                    f"## Hierarchical Data for {contrib['identifier']}"
                ),
                nbf.new_code_cell(
                    "HierarchicalData(contrib['content'])"
                )
            ]

            tables = contrib.content['tables']
            if tables:
                cells.append(nbf.new_markdown_cell(
                    f"## Tabular Data for {contrib['identifier']}"
                ))
                for ref in tables:
                    cells.append(nbf.new_code_cell(
                        f"table = client.tables.get_entry(tid='{ref.id}').response().result # Pandas DataFrame format\n"
                        "Table.from_dict(table)"
                    ))
                    cells.append(nbf.new_code_cell(
                        "Plot.from_dict(table)"
                    ))

            structures = contrib.content['structures']
            if structures:
                cells.append(nbf.new_markdown_cell(
                    f"## Pymatgen Structures for {contrib['identifier']}"
                ))
                for ref in structures:
                    cells.append(nbf.new_code_cell(
                        f"Structure.from_dict(client.structures.get_entry(sid='{ref.id}').response().result)"
                    ))

            kernel = client.start_kernel()
            for cell in cells:
                if cell.cell_type == 'code':
                    cell.outputs = kernel.execute(cell.source)
            client.shutdown_kernel(kernel)

            nb = deepcopy(seed_nb)
            nb.cells += cells
            nb = Notebooks(**nb)
            nb.id = cid  # to link to the according contribution
            nb.save()  # calls Notebooks.clean()

        del nb.id
        return nb

    # def delete(self, project, cids):
    #     for contrib in self.contributions.find({'_id': {'$in': cids}}):
    #         identifier, cid = contrib['identifier'], contrib['_id']
    #         coll = self.notebooks
    #         key = '.'.join([project, str(cid)])
    #         coll.update({}, {'$unset': {key: 1}}, multi=True)
    #     # remove `project` field when no contributions remaining
    #     for coll in [self.materials, self.compositions]:
    #         for doc in coll.find({project: {'$exists': 1}}):
    #             for d in doc.itervalues():
    #                 if not d:
    #                     coll.update({'_id': doc['_id']}, {'$unset': {project: 1}})


# url_prefix added in register_blueprint
single_view = NotebookView.as_view(NotebookView.__name__)
notebooks.add_url_rule('/<string:cid>', view_func=single_view, methods=['GET'])
