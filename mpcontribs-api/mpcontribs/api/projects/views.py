from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects

projects = Blueprint("projects", __name__)

class ProjectsView(SwaggerView):

    def get(self):
        """Retrieve (and optionally filter) projects.
        ---
        operationId: get_entries
        parameters:
            - name: search
              in: query
              type: string
              description: string to search for in `title`, `description`, and \
                      `authors` using a MongoEngine/MongoDB text index. Provide \
                      a space-separated list to the search query parameter to \
                      search for multiple words. For more, see \
                      https://docs.mongodb.com/manual/text-search/.
            - name: mask
              in: query
              type: array
              items:
                  type: string
              default: ["project", "title"]
              description: comma-separated list of fields to return (MongoDB syntax)
        responses:
            200:
                description: list of projects
                schema:
                    type: array
                    items:
                        $ref: '#/definitions/ProjectsSchema'
        """
        mask = request.args.get('mask', 'project,title').split(',')
        objects = Projects.objects.only(*mask)
        search = request.args.get('search')
        entries = objects.search_text(search) if search else objects.all()
        return self.marshal(entries)

    # TODO: only staff can start new project
    def post(self):
        """Create a new project.
        Only MP staff can submit a new/non-existing project (or use POST
        endpoints in general). The staff member's email address will be set as
        the first readWrite entry in the permissions dict.
        """
        return NotImplemented()


class ProjectView(SwaggerView):

    def get(self, project):
        """Retrieve a single project.
        ---
        operationId: get_entry
        parameters:
            - name: project
              in: path
              type: string
              pattern: '^[a-zA-Z0-9_]{3,30}$'
              required: true
              description: get provenance entry for a project (name/slug)
        responses:
            200:
                description: single project
                schema:
                    $ref: '#/definitions/ProjectsSchema'
        """
        return self.marshal(Projects.objects.get(project=project))

    # TODO: only emails with readWrite permissions can use methods below
    def put(self, project):
        """Replace a project's provenance entry"""
        # TODO id/project are read-only
        return NotImplemented()

    def patch(self, project):
        """Partially update a project's provenance entry"""
        return NotImplemented()
        schema = self.Schema(dump_only=('id', 'project')) # id/project read-only
        schema.opts.model_build_obj = False
        payload = schema.load(request.json, partial=True)
        if payload.errors:
            return payload.errors # TODO raise JsonError 400?
        # set fields defined in model
        if 'urls' in payload.data:
            urls = payload.data.pop('urls')
            payload.data.update(dict(
                ('urls__'+key, getattr(urls, key)) for key in urls
            ))
        # set dynamic fields for urls
        for key, url in request.json.get('urls', {}).items():
            payload.data['urls__'+key] = url
        return payload.data
        #Projects.objects(project=project).update(**payload.data)

    def delete(self, project):
        """Delete a project's provenance entry"""
        # TODO should also delete all contributions
        return NotImplemented()

# url_prefix added in register_blueprint
# also see http://flask.pocoo.org/docs/1.0/views/#method-views-for-apis
multi_view = ProjectsView.as_view(ProjectsView.__name__)
projects.add_url_rule('/', view_func=multi_view, methods=['GET'])#, 'POST'])

single_view = ProjectView.as_view(ProjectView.__name__)
projects.add_url_rule('/<string:project>', view_func=single_view,
                         methods=['GET'])#, 'PUT', 'PATCH', 'DELETE'])
