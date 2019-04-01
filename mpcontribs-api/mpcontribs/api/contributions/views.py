from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions

contributions = Blueprint("contributions", __name__)

class ContributionsView(SwaggerView):
    # TODO http://docs.mongoengine.org/guide/querying.html#raw-queries

    def get(self):
        """Retrieve (and optionally filter) contributions.
        ---
        operationId: get_entries
        parameters:
            - name: project
              in: query
              type: string
              description: retrieve contributions for specific project
            - name: page
              in: query
              type: integer
              default: 1
              description: page to retrieve (in batches of 20)
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["project", "identifier"]
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: list of contributions
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ContributionsSchema'
        """
        mask = request.args.get('mask', 'project,identifier').split(',')
        objects = Contributions.objects.only(*mask)
        page = int(request.args.get('page', 1))
        project = request.args.get('project')
        if project:
            objects = objects(project=project)
        entries = objects.paginate(page=page, per_page=20).items
        return self.marshal(entries)

    def options(self):
        """Retrieve distinct list of identifiers
        ---
        operationId: distinct
        responses:
            200:
                description: list of contributed materials/compositions
                schema:
                    type: array
                    items:
                        type: string
        """
        return Contributions.objects.distinct('identifier')

# url_prefix added in register_blueprint
multi_view = ContributionsView.as_view(ContributionsView.__name__)
contributions.add_url_rule('/', view_func=multi_view, methods=['GET', 'OPTIONS'])#, 'POST'])
