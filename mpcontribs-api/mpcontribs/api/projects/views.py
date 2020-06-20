# -*- coding: utf-8 -*-
import os
import flask_mongorest
from marshmallow.utils import get_value
from mongoengine.queryset import DoesNotExist
from flask import Blueprint, current_app, url_for
from flask_mongorest.exceptions import UnknownFieldError
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import *
from werkzeug.exceptions import Unauthorized
from itsdangerous import SignatureExpired
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.structures.document import Structures

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
projects = Blueprint("projects", __name__, template_folder=templates)


class ProjectsResource(Resource):
    document = Projects
    filters = {
        "project": [ops.In, ops.Exact, ops.IContains],
        "is_public": [ops.Boolean],
        "title": [ops.IContains],
        "long_title": [ops.IContains],
        "authors": [ops.IContains],
        "description": [ops.IContains],
        "owner": [ops.Exact, ops.In],
        "is_approved": [ops.Boolean],
        "unique_identifiers": [ops.Boolean],
    }
    fields = [
        "project",
        "is_public",
        "title",
        "owner",
        "is_approved",
        "unique_identifiers",
    ]
    allowed_ordering = ["project", "is_public", "title"]
    paginate = False

    @staticmethod
    def get_optional_fields():
        return ["long_title", "authors", "description", "urls", "other", "columns"]

    def value_for_field(self, obj, field):
        # add columns key to response if requested
        if field == "columns":
            objects = list(
                Contributions.objects.aggregate(
                    *[
                        {"$match": {"project": obj.id}},
                        # NOTE contributors need to make sure that all columns are
                        #      included in first 20 contributions
                        {"$limit": 20},
                        {"$project": {"_id": 0, "akv": {"$objectToArray": "$data"}}},
                        {"$unwind": "$akv"},
                        {
                            "$project": {
                                "root": "$akv.k",
                                "level2": {
                                    "$switch": {
                                        "branches": [
                                            {
                                                "case": {
                                                    "$eq": [
                                                        {"$type": "$akv.v"},
                                                        "object",
                                                    ]
                                                },
                                                "then": {"$objectToArray": "$akv.v"},
                                            }
                                        ],
                                        "default": [{}],
                                    }
                                },
                            }
                        },
                        {"$unwind": "$level2"},
                        {
                            "$project": {
                                "column": {
                                    "$switch": {
                                        "branches": [
                                            {
                                                "case": {"$eq": ["$level2", {}]},
                                                "then": "$root",
                                            },
                                            {
                                                "case": {
                                                    "$eq": ["$level2.k", "display"]
                                                },
                                                "then": "$root",
                                            },
                                            {
                                                "case": {"$eq": ["$level2.k", "value"]},
                                                "then": "$root",
                                            },
                                            {
                                                "case": {"$eq": ["$level2.k", "unit"]},
                                                "then": "$root",
                                            },
                                        ],
                                        "default": {
                                            "$concat": ["$root", ".", "$level2.k"]
                                        },
                                    }
                                }
                            }
                        },
                    ]
                )
            )

            # neither $group nor set maintain order! Dicts are ordered in python 3.7+
            columns = {}
            for col in list(dict.fromkeys(o["column"] for o in objects)):
                value_field, unit_field = f"data.{col}.value", f"data.{col}.unit"
                unit_query = {
                    "project": obj.id,
                    f'data__{col.replace(".", "__")}__exists': True,
                }
                unit_contribs = Contributions.objects.only(unit_field).filter(
                    **unit_query
                )
                unit_sample = unit_contribs.limit(-1).first()
                min_max = list(
                    Contributions.objects.aggregate(
                        *[
                            {
                                "$match": {
                                    "project": obj.id,
                                    value_field: {"$exists": True},
                                }
                            },
                            {
                                "$group": {
                                    "_id": None,
                                    "max": {"$max": f"${value_field}"},
                                    "min": {"$min": f"${value_field}"},
                                }
                            },
                        ]
                    )
                )
                rng = [min_max[0]["min"], min_max[0]["max"]] if min_max else None
                unit = get_value(unit_sample, unit_field)
                if min_max and unit is None:
                    unit = ""  # catch missing unit field in data
                key = f"data.{col} [{unit}]" if min_max else f"data.{col}"
                columns[key] = rng

            contributions = Contributions.objects.only("pk").filter(project=obj.id)
            agg = list(
                Structures.objects.aggregate(
                    *[
                        {
                            "$match": {
                                "contribution": {"$in": [c.pk for c in contributions]}
                            }
                        },
                        {
                            "$group": {
                                "_id": "$contribution",
                                "count": {"$sum": 1},
                                "labels": {"$addToSet": "$label"},
                            }
                        },
                        {"$sort": {"count": -1}},
                        {"$limit": 1},
                    ]
                )
            )
            if agg:
                for label in agg[0]["labels"]:
                    columns[f"structures.{label}"] = None

            obj.update(set__columns=columns)  # save for look-up on subsequent requests
            return columns
        else:
            raise UnknownFieldError


class ProjectsView(SwaggerView):
    resource = ProjectsResource
    methods = [Fetch, Create, Delete, Update, BulkFetch]

    def has_add_permission(self, request, obj):
        # limit the number of projects a user can own (unless admin)
        if "admin" in self.get_groups(request):
            return True
        # project already created at this point -> count-1 and revert
        nr_projects = Projects.objects(owner=obj.owner).count() - 1
        if nr_projects > 2:
            Projects.objects(project=obj.project).delete()
            raise Unauthorized(f"{obj.owner} already owns {nr_projects} projects.")
        return True


@projects.route("/applications/<token>", defaults={"action": None})
@projects.route("/applications/<token>/<action>")
def applications(token, action):
    ts = current_app.config["USTS"]
    max_age = current_app.config["USTS_MAX_AGE"]
    try:
        owner, project = ts.loads(token, max_age=max_age)
    except SignatureExpired:
        return f"signature for {owner} of {project} expired."

    try:
        obj = Projects.objects.get(project=project, owner=owner, is_approved=False)
    except DoesNotExist:
        return f"{project} for {owner} already approved or denied."

    actions = ["approve", "deny"]
    if action not in actions:
        response = f"<h3>{project}</h3><ul>"
        scheme = "http" if current_app.config["DEBUG"] else "https"
        for a in actions:
            u = url_for(
                "projects.applications",
                token=token,
                action=a,
                _scheme=scheme,
                _external=True,
            )
            response += f'<li><a href="{u}">{a}</a></li>'
        return response + "</ul>"

    if action == "approve":
        obj.is_approved = True
        obj.save()  # post_save (created=False) sends notification when `is_approved` set
    else:
        obj.delete()  # post_delete signal sends notification

    return f'{project} {action.replace("y", "ie")}d and {owner} notified.'
