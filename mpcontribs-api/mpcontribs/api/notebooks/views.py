import os
from flask import Blueprint
from mongoengine import DoesNotExist
from nbformat import v4 as nbf
from nbconvert.preprocessors import ExecutePreprocessor
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks

notebooks = Blueprint("notebooks", __name__)
exprep = ExecutePreprocessor(timeout=600, allow_errors=False)
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
            cells = [
                nbf.new_code_cell(
                    "# provide apikey to `load_client` in order to connect to api.mpcontribs.org\n"
                    "# or use bravado (see https://mpcontribs.org/api)\n"
                    "from mpcontribs.client import load_client\n"
                    "client = load_client()"
                ), nbf.new_code_cell(
                    "from mpcontribs.io.archieml.mpfile import MPFile\n"
                    f"result = client.contributions.get_entry(cid='{cid}').response().result\n"
                    "mpfile = MPFile.from_contribution(result)"
                )
            ]
            for typ in ['h', 't', 'g', 's']:
                cells.append(nbf.new_code_cell(f"mpfile.{typ}data"))
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
