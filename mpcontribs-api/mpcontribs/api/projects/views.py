# -*- coding: utf-8 -*-
import os
import flask_mongorest

from mongoengine.queryset import DoesNotExist
from flask import Blueprint, current_app, url_for, jsonify, abort, request
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, Create, Delete, Update, BulkFetch
from werkzeug.exceptions import Unauthorized

from mpcontribs.api import FILTERS
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects, Column, Reference, Stats

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
projects = Blueprint("projects", __name__, template_folder=templates)
MAX_PROJECTS = os.environ.get("MAX_PROJECTS", 3)


class ColumnResource(Resource):
    document = Column


class ReferenceResource(Resource):
    document = Reference


class StatsResource(Resource):
    document = Stats


class ProjectsResource(Resource):
    document = Projects
    related_resources = {
        "columns": ColumnResource,
        "references": ReferenceResource,
        "stats": StatsResource,
    }
    filters = {
        "name": FILTERS["STRINGS"],
        "is_public": [ops.Boolean],
        "title": FILTERS["STRINGS"],
        "long_title": FILTERS["LONG_STRINGS"],
        "authors": FILTERS["LONG_STRINGS"],
        "description": FILTERS["LONG_STRINGS"],
        "owner": FILTERS["STRINGS"],
        "license": FILTERS["STRINGS"],
        "is_approved": [ops.Boolean],
        "unique_identifiers": [ops.Boolean],
        "columns": [ops.Size],
        "stats__columns": FILTERS["NUMBERS"],
        "stats__contributions": FILTERS["NUMBERS"],
        "stats__tables": FILTERS["NUMBERS"],
        "stats__structures": FILTERS["NUMBERS"],
        "stats__attachments": FILTERS["NUMBERS"],
        "stats__size": FILTERS["NUMBERS"],
    }
    fields = [
        "name",
        "is_public",
        "title",
        "owner",
        "is_approved",
        "unique_identifiers",
    ]
    allowed_ordering = ["name", "is_public", "title"]
    paginate = True
    default_limit = 100
    max_limit = 500

    @staticmethod
    def get_optional_fields():
        return [
            "long_title",
            "authors",
            "description",
            "references",
            "license",
            "other",
            "columns",
            "stats",
        ]


class ProjectsView(SwaggerView):
    resource = ProjectsResource
    methods = [Fetch, Create, Delete, Update, BulkFetch]

    def has_add_permission(self, req, obj):
        if self.is_anonymous(req):
            return False

        obj.owner = req.headers.get("X-Consumer-Username")
        groups = self.get_groups(req)
        is_admin = self.is_admin(groups)
        if is_admin:
            return True

        # is_approved can only be set by an admin
        if obj.is_approved:
            raise Unauthorized(f"Only admins can set `is_approved=True`")

        # limit the number of projects a user can own (unless admin)
        nr_projects = Projects.objects(owner=obj.owner).count()
        if nr_projects > MAX_PROJECTS:
            raise Unauthorized(f"{obj.owner} already owns {nr_projects} projects.")

        return True

    def has_change_permission(self, req, obj):
        if not self.is_admin_or_project_user(req, obj):
            return False

        # is_public can only be changed if project is_approved
        if obj.is_public and not obj.is_approved:
            raise Unauthorized(f"{obj.id} is not approved yet.")

        return True


@projects.route("/applications/<token>", defaults={"action": None})
@projects.route("/applications/<token>/<action>")
def applications(token, action):
    ts = current_app.config["USTS"]
    owner, project = ts.loads(token)

    try:
        obj = Projects.objects.get(name=project, owner=owner, is_approved=False)
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
        obj.reload(*obj._fields.keys())
        obj.is_approved = True
        obj.save()  # post_save (created=False) sends notification when `is_approved` set
    else:
        obj.delete()  # post_delete signal sends notification

    return f'{project} {action.replace("y", "ie")}d and {owner} notified.'


@projects.route("/search")
def search():
    term = request.args.get("term")
    if not term:
        abort(404, description="Missing search term.")

    pipeline = [{
        "$search": {
            "index": "mpcontribs-dev-project-search",
            "text": {"path": {"wildcard": "*"}, "query": term}
        }
    }, {"$project": {"_id": 1}}]
    result = [p["_id"] for p in Projects.objects().aggregate(pipeline)]
    return jsonify(result)
