import os
import flask_mongorest
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update, BulkUpdate
from flask import Blueprint

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions, Contents
from mpcontribs.api.contributions.redox_thermo_csp_views import isograph_view, energy_analysis_view

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
contributions = Blueprint("contributions", __name__, template_folder=templates)


class ContentsResource(Resource):
    document = Contents


class ContributionsResource(Resource):
    document = Contributions
    related_resources = {'content': ContentsResource}
    filters = {
        'project': [ops.In, ops.Exact],
        'identifier': [ops.In, ops.IContains],
        'content__data__formula': [ops.Contains],
        'content__data__C__value': [ops.Gt]
        #query = construct_query(filters) # TODO how to define filters on content?
    }
    fields = ['id', 'project', 'identifier']
    allowed_ordering = ['project', 'identifier']
    paginate = True
    default_limit = 20
    max_limit = 200
    bulk_update_limit = 100

    @staticmethod
    def get_optional_fields():
        return ['content']


class ContributionsView(SwaggerView):
    resource = ContributionsResource
    methods = [List, Fetch, Create, Delete, Update, BulkUpdate]
    # TODO unpack display from dict
    # https://github.com/tschaume/flask-mongorest/blob/9a04099daf9a93eefd6fd2ee906c29ffbb87789f/flask_mongorest/resources.py#L401
    # unflatten(dict(
    #     (k, v) for k, v in get_cleaned_data(<serialize_dict_field>).items()
    # ))


#class ModalView(SwaggerView):
#    resource = ContributionsResource
#
#    def get(self, cid):
#        """Retrieve modal data for a single contribution.
#        ---
#        operationId: get_modal_data
#        parameters:
#            - name: cid
#              in: path
#              type: string
#              pattern: '^[a-f0-9]{24}$'
#              required: true
#              description: contribution ID (ObjectId)
#        responses:
#            200:
#                description: modal data as defined by contributor
#                schema:
#                    type: object
#        """
#        mask = ['project', 'identifier', 'content.data.modal']
#        contrib = Contributions.objects.only(*mask).get(id=cid)
#        data = contrib.content.data
#        if 'modal' not in data:
#            return {}
#        return unflatten(get_cleaned_data(data))
#
#
#modal_view = ModalView.as_view(ModalView.__name__)
#contributions.add_url_rule('/<string:cid>/modal', view_func=modal_view, methods=['GET'])

contributions.add_url_rule('/redox_thermo_csp_energy/',
                           view_func=energy_analysis_view, methods=['GET'])
contributions.add_url_rule('/<string:cid>/redox_thermo_csp/<string:plot_type>',
                           view_func=isograph_view, methods=['GET'])
