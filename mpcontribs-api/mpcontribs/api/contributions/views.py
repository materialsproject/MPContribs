from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions

contributions = Blueprint("contributions", __name__)

class ContributionsView(SwaggerView):
    """defines methods for API operations with contributions"""

    def get(self):
        """Retrieve (and optionally filter) contributions.
        ---
        parameters:
            - name: project
              in: query
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: project identifier (name/slug)
        responses:
            200:
                description: list of contributions
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ContributionsSchema'
        """
        # TODO http://docs.mongoengine.org/guide/querying.html#raw-queries
        # TODO make HEADER option or query paramater?
        mask = ['project', 'identifier']#, 'collaborators']
        objects = Contributions.objects.only(*mask)
        # TODO remove first() to return all contributions for project
        entries = objects(project=request.args['project']).first()
        return self.marshal(entries)

# url_prefix added in register_blueprint
contributions.add_url_rule(
    '/', view_func=ContributionsView.as_view(ContributionsView.__name__),
    methods=['GET']#, 'POST', 'PUT', 'PATCH', 'DELETE']
)
