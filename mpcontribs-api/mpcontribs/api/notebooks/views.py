import os
from flask import Blueprint
from mongoengine import DoesNotExist
from nbformat import v4 as nbf
from nbconvert.preprocessors import ExecutePreprocessor
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.contributions.document import Contributions

notebooks = Blueprint("notebooks", __name__)
exprep = ExecutePreprocessor(timeout=600, allow_errors=False)
exprep.log.setLevel('DEBUG')
exprep.enabled = True

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
            contrib = Contributions.objects.no_dereference().get(id=cid)
            cells = [
                nbf.new_code_cell(
                    "from mpcontribs.client import load_client\n"
                    "client = load_client() # provide apikey as argument to use api.mpcontribs.org\n"
                    f"contrib = client.contributions.get_entry(cid='{cid}').response().result"
                ),
                nbf.new_markdown_cell("## Provenance Info"),
                nbf.new_code_cell(
                    "from mpcontribs.io.core.recdict import RecursiveDict\n"
                    "mask = ['title', 'authors', 'description', 'urls', 'other', 'project']\n"
                    "prov = client.projects.get_entry(project=contrib['project'], mask=mask).response().result\n"
                    "RecursiveDict(prov)"
                ),
                nbf.new_markdown_cell(
                    f"## Hierarchical Data for {contrib['identifier']}"
                ),
                nbf.new_code_cell(
                    "from mpcontribs.io.core.components.hdata import HierarchicalData\n"
                    "HierarchicalData(contrib['content'])"
                )
            ]

            tables = contrib.content['tables']
            if tables:
                cells.append(nbf.new_markdown_cell(
                    f"## Tabular Data for {contrib['identifier']}"
                ))
                cells.append(nbf.new_code_cell(
                    "# - table IDs `tid` are in `contrib['content']['tables']`\n"
                    "# - set `per_page` query parameter to retrieve up to 200 rows at once (paginate for more)\n"
                    "from mpcontribs.io.core.components.tdata import Table # DataFrame with Backgrid IPython Display\n"
                    "from mpcontribs.io.core.components.gdata import Plot # Plotly interactive graph"
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
                cells.append(nbf.new_code_cell(
                    "# structure IDs `sid` are in `contrib['content']['structures']`\n"
                    "from pymatgen import Structure\n"
                ))
                for ref in structures:
                    cells.append(nbf.new_code_cell(
                        f"Structure.from_dict(client.structures.get_entry(sid='{ref.id}').response().result)"
                    ))

            nb = nbf.new_notebook()
            nb['cells'] = cells
            exprep.preprocess(nb, {})
            nb = Notebooks(**nb)
            nb.id = cid # to link to the according contribution
            nb.save() # calls Notebooks.clean()

        del nb.id
        return nb

    #def delete(self, project, cids):
    #    for contrib in self.contributions.find({'_id': {'$in': cids}}):
    #        identifier, cid = contrib['identifier'], contrib['_id']
    #        coll = self.notebooks
    #        key = '.'.join([project, str(cid)])
    #        coll.update({}, {'$unset': {key: 1}}, multi=True)
    #    # remove `project` field when no contributions remaining
    #    for coll in [self.materials, self.compositions]:
    #        for doc in coll.find({project: {'$exists': 1}}):
    #            for d in doc.itervalues():
    #                if not d:
    #                    coll.update({'_id': doc['_id']}, {'$unset': {project: 1}})

# url_prefix added in register_blueprint
single_view = NotebookView.as_view(NotebookView.__name__)
notebooks.add_url_rule('/<string:cid>', view_func=single_view, methods=['GET'])
