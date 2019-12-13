import os
import flask_mongorest
from dict_deep import deep_get
from mongoengine.queryset.visitor import Q
from mongoengine.queryset import DoesNotExist
from flask import Blueprint, request, current_app
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import List, Fetch, Create, Delete, Update
from pandas.io.json._normalize import nested_to_record
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
        'title': [ops.IContains],
        'description': [ops.IContains],
        'authors': [ops.IContains]
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

            if not objects:
                return []

            columns = []
            for col in objects[0]['columns']:
                if not col.startswith('modal.'):
                    unit_field = f'data.{col}.unit'
                    unit_query = {f'data__{col.replace(".", "__")}__exists': True}
                    unit_sample = Contributions.objects.only(unit_field).filter(**unit_query).first()
                    try:
                        unit = deep_get(unit_sample, unit_field)
                        columns.append(f'{col} [{unit}]')
                    except KeyError:  # column doesn't have a unit
                        columns.append(col)

            projects = sorted(obj.id.split('_'))
            names = Structures.objects(project=obj.id).distinct("name")
            if names:
                if len(projects) == len(names):
                    for p, n in zip(projects, sorted(names)):
                        if p == n.lower():
                            columns.append(f'{n}.CIF')
                else:
                    columns.append('CIF')

            return sorted(columns)
        else:
            raise UnknownFieldError


class ProjectsView(SwaggerView):
    resource = ProjectsResource
    methods = [List, Fetch, Create, Delete, Update]

    def has_add_permission(self, request, obj):
        # limit the number of projects a user can own (unless admin)
        return 'admin' in self.get_groups(request) or Projects.objects.count(owner=obj.owner) < 5
