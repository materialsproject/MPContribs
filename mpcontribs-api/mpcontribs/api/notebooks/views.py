import os
from flask import Blueprint
from mongoengine import DoesNotExist
from nbformat import v4 as nbf
from nbconvert.preprocessors import ExecutePreprocessor
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.notebooks.document import Notebooks

notebooks = Blueprint("notebooks", __name__)
exprep = ExecutePreprocessor(timeout=600, allow_errors=False)

class NotebookView(SwaggerView):

    def get(self, cid):
        """Retrieve (and build) notebook for a single contribution.
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
            return Notebooks.objects.get(id=cid)
        except DoesNotExist:
            print('building notebook ...')
            cells = [
                nbf.new_code_cell(
                    "from mpcontribs.client import load_client\n"
                    "client = load_client() # provide apikey to connect to api.mpcontribs.org"
                ), nbf.new_code_cell(
                    "from mpcontribs.io.archieml.mpfile import MPFile\n"
                    f"result = client.contributions.get_entry(cid='{cid}').response().result\n"
                    "mpfile = MPFile.from_contribution(result)\n"
                    "identifier = mpfile.ids[0]\n"
                    "mpfile.gdata[identifier]"
                )
            ]
            #for typ in ['h', 't', 'g', 's']:
            #    cells.append(nbf.new_code_cell(f"mpfile.{typ}data[identifier]"))
            nb = nbf.new_notebook()
            nb['cells'] = cells
            nbdir = os.path.dirname(os.path.abspath(__file__))
            exprep.preprocess(nb, {'metadata': {'path': nbdir}})
            print(nb)
            Notebooks(**nb).save()
            # TODO commit nb to database
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
