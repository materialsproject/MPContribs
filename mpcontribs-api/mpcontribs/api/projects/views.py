import os
import flask_mongorest
from dict_deep import deep_get
from mongoengine.queryset.visitor import Q
from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app, url_for
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update
from werkzeug.exceptions import Unauthorized
from pandas.io.json._normalize import nested_to_record
from itsdangerous import BadSignature, SignatureExpired
from mpcontribs.api import construct_query
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.document import Structures

templates = os.path.join(
    os.path.dirname(flask_mongorest.__file__), 'templates'
)
projects = Blueprint("projects", __name__, template_folder=templates)


class ProjectsResource(Resource):
    document = Projects
    filters = {
        'project': [ops.Exact, ops.IContains],
        'is_public': [ops.Boolean],
        'title': [ops.Exact, ops.IContains],
        'authors': [ops.IContains],
        'description': [ops.IContains],
        'owner': [ops.Exact],
        'is_approved': [ops.Boolean]
    }
    fields = ['project', 'is_public', 'title', 'owner', 'is_approved']
    allowed_ordering = ['project', 'is_public', 'title']
    paginate = False

    @staticmethod
    def get_optional_fields():
        return ['authors', 'description', 'urls', 'other', 'columns']

    def value_for_field(self, obj, field):
        # add columns key to response if requested
        if field == 'columns':
            objects = list(Contributions.objects.aggregate(*[
                {"$match": {"project": obj.id}},
                {"$limit": 999},
                {"$project": {"akv": {"$objectToArray": "$data"}}},
                {"$unwind": "$akv"},
                {"$project": {"root": "$akv.k", "level2": {
                    "$switch": {"branches": [{
                        "case": {"$eq": [{"$type": "$akv.v"}, "object"]},
                        "then": {"$objectToArray": "$akv.v"}
                    }], "default": [{}]}
                }}},
                {"$unwind": "$level2"},
                {"$project": {"column": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": ["$level2", {}]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "display"]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "value"]}, "then": "$root"},
                            {"case": {"$eq": ["$level2.k", "unit"]}, "then": "$root"},
                        ],
                        "default": {"$concat": ["$root", ".", "$level2.k"]}
                    }
                }}},
                {"$group": {"_id": None, "columns": {"$addToSet": "$column"}}}
            ]))

            columns = {}

            if objects:
                for col in objects[0]['columns']:
                    value_field, unit_field = f'data.{col}.value', f'data.{col}.unit'
                    unit_query = {'project': obj.id, f'data__{col.replace(".", "__")}__exists': True}
                    unit_sample = Contributions.objects.only(unit_field).filter(**unit_query).limit(-1).first()
                    min_max = list(Contributions.objects.aggregate(*[
                        {"$match": {"project": obj.id, value_field: {'$exists': True}}},
                        { "$group": {
                            "_id": None, "max": {"$max": f"${value_field}"}, "min": {"$min": f"${value_field}"}
                        }}
                    ]))
                    rng = None
                    if min_max:
                        rng = [min_max[0]['min'], min_max[0]['max']]
                    try:
                        unit = deep_get(unit_sample, unit_field)
                        columns[f'{col} [{unit}]'] = rng
                    except KeyError:  # column doesn't have a unit
                        columns[col] = rng

            contributions = Contributions.objects.only('pk').filter(project=obj.id)
            agg = list(Structures.objects.aggregate(*[
                {'$match': {'contribution': {'$in': [c.pk for c in contributions]}}},
                {'$group': {'_id': '$contribution', 'count': {'$sum': 1}, 'names': {'$addToSet': '$name'}}},
                {'$sort': {'count': -1}}, {'$limit': 1}
            ]))
            if agg:
                # check for structures linked to sub-projects
                max_doc = agg[0]
                projects = sorted(obj.id.split('_'))
                if max_doc['count'] > 1 and len(projects) == max_doc['count']:
                    for p, n in zip(projects, sorted(max_doc['names'])):
                        if p == n.lower():
                            columns[f'{n}.CIF'] = None
                            max_doc['names'].remove(n)
                # add remaining structures
                remain = len(max_doc['names'])
                if remain > 1:
                    for idx, name in enumerate(max_doc['names']):
                        # TODO find better lable than numbering - needed for perovskites_diffusion?
                        columns[f'#{idx+1} CIF'] = None
                elif remain == 1:
                    # name is irrelevant if only one structure per contrib
                    columns[f'CIF'] = None

            return dict(sorted(columns.items(), key=lambda t: t[0]))
        else:
            raise UnknownFieldError


class ProjectsView(SwaggerView):
    resource = ProjectsResource
    methods = [List, Fetch, Create, Delete, Update]

    def has_add_permission(self, request, obj):
        # limit the number of projects a user can own (unless admin)
        if 'admin' in self.get_groups(request):
            return True
        # project already created at this point -> count-1 and revert
        nr_projects = Projects.objects(owner=obj.owner).count() - 1
        if nr_projects > 2:
            Projects.objects(project=obj.project).delete()
            raise Unauthorized(f'{obj.owner} already owns {nr_projects} projects.')
        return True


@projects.route('/applications/<token>', defaults={'action': None})
@projects.route('/applications/<token>/<action>')
def applications(token, action):
    ts = current_app.config['USTS']
    max_age = current_app.config['USTS_MAX_AGE']
    try:
        owner, project = ts.loads(token, max_age=max_age)
    except SignatureExpired:
        return f'signature for {owner} of {project} expired.'

    try:
        obj = Projects.objects.get(project=project, owner=owner, is_approved=False)
    except DoesNotExist:
        return f'{project} for {owner} already approved or denied.'

    actions = ['approve', 'deny']
    if action not in actions:
        response = f'<h3>{project}</h3><ul>'
        for a in actions:
            u = url_for('projects.applications', token=token, action=a, _external=True)
            response += f'<li><a href="{u}">{a}</a></li>'
        return response + '</ul>'

    if action == 'approve':
        obj.is_approved = True
        obj.save()  # post_save (created=False) sends notification when `is_approved` set
    else:
        obj.delete()  # post_delete signal sends notification

    return f'{project} {action.replace("y", "ie")}d and {owner} notified.'
