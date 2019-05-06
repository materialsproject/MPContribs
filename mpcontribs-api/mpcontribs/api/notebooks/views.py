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
            contrib = Contributions.objects.get(id=cid)
            cells = [
                nbf.new_code_cell(
                    "from mpcontribs.client import load_client\n"
                    "client = load_client() # provide apikey as argument to use api.mpcontribs.org\n"
                    f"contrib = client.contributions.get_entry(cid='{cid}').response().result"
                ),
                nbf.new_markdown_cell(
                    f"## Provenance for Project {contrib['project']}"
                ),
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

            ntables = len(contrib.content['tables'])
            if ntables:
                cells.append(nbf.new_markdown_cell(
                    f"## Tabular Data for {contrib['identifier']}"
                ))
                cells.append(nbf.new_code_cell(
                    "# set `per_page` to retrieve up to 200 rows at once (paginate for more)\n"
                    "raw_tables = [\n"
                    "\tclient.tables.get_entry(tid=tid).response().result\n"
                    "\tfor tid in contrib['content']['tables']\n"
                    "]\n"
                    "from mpcontribs.io.core.components.tdata import Table\n"
                    "tables = {}"
                ))
                for n in range(ntables):
                    cells.append(nbf.new_code_cell(
                        f"table = raw_tables[{n}]\n"
                        "tables[table['name']] = Table.from_dict(table) # DataFrame with Backgrid IPython Display\n"
                        "tables[table['name']]"
                    ))

            ngraphs = len(contrib.content['graphs'])
            if ngraphs:
                cells.append(nbf.new_markdown_cell(
                    f"## Graphs for {contrib['identifier']}"
                ))
                cells.append(nbf.new_code_cell(
                    "from mpcontribs.io.core.components.gdata import Plot\n"
                    "graphs = [\n"
                    "\tPlot(conf, tables[conf['table']])\n"
                    "\tfor k, conf in contrib['content']['graphs'].items()\n"
                    "]"
                ))
                for n in range(ngraphs):
                    cells.append(nbf.new_code_cell(
                        f"graphs[{n}] # Plotly interactive graph"
                    ))

            nstructures = len(contrib.content['structures'])
            if nstructures:
                cells.append(nbf.new_markdown_cell(
                    f"## Structures for {contrib['identifier']}"
                ))
                cells.append(nbf.new_code_cell(
                    "from pymatgen import Structure\n"
                    "structures = [Structure.from_dict(\n"
                    "\tclient.structures.get_entry(sid=sid).response().result\n"
                    ") for sid in contrib['content']['structures']]\n"
                ))
                for n in range(nstructures):
                    cells.append(nbf.new_code_cell(
                        f"structures[{n}] # Pymatgen Structure"
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
