# -*- coding: utf-8 -*-
"""Custom meta-class and MethodView for Swagger"""

import os
import yaml

from copy import deepcopy
from re import Pattern
from importlib import import_module
from flasgger.marshmallow_apispec import SwaggerView as OriginalSwaggerView
from flasgger.marshmallow_apispec import schema2jsonschema
from marshmallow_mongoengine import ModelSchema
from flask_mongorest.views import ResourceView
from mongoengine.queryset import DoesNotExist
from mongoengine.queryset.visitor import Q
from werkzeug.exceptions import Unauthorized
from mpcontribs.api.config import DOC_DIR
from mpcontribs.api import is_gunicorn, get_logger

logger = get_logger(__name__)


def get_limit_params(resource, method):
    default = resource.default_limit
    bulk = {"BulkUpdate", "BulkDelete"}
    maximum = resource.bulk_update_limit if method in bulk else resource.max_limit
    return [
        {
            "name": "_skip",
            "in": "query",
            "type": "integer",
            "description": "number of items to skip",
        },
        {
            "name": "_limit",
            "in": "query",
            "type": "integer",
            "default": default,
            "maximum": maximum,
            "description": "maximum number of items to return",
        },
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "description": "page number to return (in batches of `per_page/_limit`; alternative to `_skip`)",
        },
        {
            "name": "per_page",
            "in": "query",
            "type": "integer",
            "default": default,
            "maximum": maximum,
            "description": "maximum number of items to return per page (same as `_limit`)",
        },
    ]


def get_filter_params(name, filters):
    filter_params = []
    is_pattern = isinstance(name, Pattern)
    label = name.pattern if is_pattern else name
    for op in filters:
        if op.op == "exact" and not is_pattern:
            name = label
            description = f"filter {label}"
        else:
            suffix = op.suf if hasattr(op, "suf") else op.op
            name = f"{label}__{suffix}"
            description = f"filter {label} via ${op.op}"

        filter_params.append(
            {
                "name": name,
                "in": "query",
                "type": op.typ,
                "description": description,
            }
        )
        if op.typ == "array":
            filter_params[-1]["items"] = {"type": "string"}
        if hasattr(op, "fmt"):
            filter_params[-1]["format"] = op.fmt

        if op.allow_negation:
            suffix = "not__"
            suffix += op.suf if hasattr(op, "suf") else op.op
            name = f"{label}__{suffix}"
            description = f"filter {label} via ${op.op}"
            param = deepcopy(filter_params[-1])
            param["name"] = name
            param["description"] = description
            filter_params.append(param)

    return filter_params


def get_specs(klass, method, collection):
    method_name = method.__name__ if hasattr(method, "__name__") else method
    default_response = {
        "description": "Error",
        "schema": {"type": "object", "properties": {"error": {"type": "string"}}},
    }
    id_field = klass.resource.document._meta["id_field"].capitalize()
    doc_name = collection[:-1].capitalize()
    fields_param = None
    if klass.resource.fields is not None:
        fields_avail = (
            klass.resource.fields + klass.resource.get_optional_fields() + ["_all"]
        )
        description = f"List of fields to include in response ({fields_avail})."
        description += " Use dot-notation for nested subfields."
        fields_param = {
            "name": "_fields",
            "in": "query",
            "default": klass.resource.fields,
            "type": "array",
            "items": {"type": "string"},
            "description": description,
        }

    field_pagination_params = []
    for field, limits in klass.resource.fields_to_paginate.items():
        field_pagination_params.append(
            {
                "name": f"{field}_page",
                "in": "query",
                "default": 1,
                "type": "integer",
                "description": f"page to retrieve for {field} field",
            }
        )
        field_pagination_params.append(
            {
                "name": f"{field}_per_page",
                "in": "query",
                "default": limits[0],
                "maximum": limits[1],
                "type": "integer",
                "description": f"number of items to retrieve per page for {field} field",
            }
        )

    filter_params = []
    if hasattr(klass.resource, "filters"):
        for k, v in klass.resource.filters.items():
            filter_params += get_filter_params(k, v)

    order_params = []
    if klass.resource.allowed_ordering:
        allowed_ordering = [
            o.pattern if isinstance(o, Pattern) else o
            for o in klass.resource.allowed_ordering
        ]
        order_params = [
            {
                "name": "_sort",
                "in": "query",
                "type": "string",
                "description": f"sort {collection} via {allowed_ordering}. Prepend +/- for asc/desc.",
            }
        ]

    spec = None
    if method_name == "Fetch":
        params = [
            {
                "name": "pk",
                "in": "path",
                "type": "string",
                "required": True,
                "description": f"{collection[:-1]} (primary key)",
            }
        ]
        if fields_param is not None:
            params.append(fields_param)
        params += field_pagination_params
        spec = {
            "summary": f"Retrieve a {collection[:-1]}.",
            "operationId": f"get{doc_name}By{id_field}",
            "parameters": params,
            "responses": {
                200: {
                    "description": f"single {collection} entry",
                    "schema": {"$ref": f"#/definitions/{klass.schema_name}"},
                },
                "default": default_response,
            },
        }

    elif method_name == "BulkFetch":
        params = [fields_param] if fields_param is not None else []
        params += field_pagination_params
        params += order_params
        params += filter_params
        schema_props = {
            "data": {
                "type": "array",
                "items": {"$ref": f"#/definitions/{klass.schema_name}"},
            }
        }
        if klass.resource.paginate:
            schema_props["has_more"] = {"type": "boolean"}
            schema_props["total_count"] = {"type": "integer"}
            schema_props["total_pages"] = {"type": "integer"}
            params += get_limit_params(klass.resource, method_name)
        spec = {
            "summary": f"Filter and retrieve {collection}.",
            "operationId": f"query{doc_name}s",
            "parameters": params,
            "responses": {
                200: {
                    "description": f"list of {collection}",
                    "schema": {"type": "object", "properties": schema_props},
                },
                "default": default_response,
            },
        }

    elif method_name == "Download":
        params = [
            {
                "name": "short_mime",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "MIME Download Type: gz",
                "default": "gz",
            },
            {
                "name": "format",
                "in": "query",
                "type": "string",
                "required": True,
                "description": f"download {collection} in different formats: {klass.resource.download_formats}",
            },
        ]
        params += [fields_param] if fields_param is not None else []
        params += order_params
        params += filter_params
        if klass.resource.paginate:
            params += get_limit_params(klass.resource, method_name)
        spec = {
            "summary": f"Filter and download {collection}.",
            "operationId": f"download{doc_name}s",
            "parameters": params,
            "produces": ["application/gzip"],
            "responses": {
                200: {
                    "description": f"{collection} download",
                    "schema": {"type": "file"},
                },
                "default": default_response,
            },
        }

    elif method_name == "Create":
        spec = {
            "summary": f"Create a new {collection[:-1]}.",
            "operationId": f"create{doc_name}",
            "parameters": [
                {
                    "name": f"{collection[:-1]}",
                    "in": "body",
                    "description": f"The object to use for {collection[:-1]} creation",
                    "schema": {"$ref": f"#/definitions/{klass.schema_name}"},
                }
            ],
            "responses": {
                200: {
                    "description": f"{collection[:-1]} created",
                    "schema": {"$ref": f"#/definitions/{klass.schema_name}"},
                },
                "default": default_response,
            },
        }

    elif method_name == "BulkCreate":
        spec = {
            "summary": f"Create new {collection[:-1]}(s).",
            "operationId": f"create{doc_name}s",
            "parameters": [
                {
                    "name": f"{collection}",
                    "in": "body",
                    "description": f"The objects to use for {collection[:-1]} creation",
                    "schema": {
                        "type": "array",
                        "items": {"$ref": f"#/definitions/{klass.schema_name}"},
                    },
                }
            ],
            "responses": {
                200: {
                    "description": f"{collection} created",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "data": {
                                "type": "array",
                                "items": {"$ref": f"#/definitions/{klass.schema_name}"},
                            },
                        },
                    },
                },
                "default": default_response,
            },
        }

    elif method_name == "Update":
        spec = {
            "summary": f"Update a {collection[:-1]}.",
            "operationId": f"update{doc_name}By{id_field}",
            "parameters": [
                {
                    "name": "pk",
                    "in": "path",
                    "type": "string",
                    "required": True,
                    "description": f"The {collection[:-1]} (primary key) to update",
                },
                {
                    "name": f"{collection[:-1]}",
                    "in": "body",
                    "description": f"The object to use for {collection[:-1]} update",
                    "schema": {"type": "object"},
                },
            ],
            "responses": {
                200: {
                    "description": f"{collection[:-1]} updated",
                    "schema": {"$ref": f"#/definitions/{klass.schema_name}"},
                },
                "default": default_response,
            },
        }
    elif method_name == "BulkUpdate":
        params = filter_params
        params.append(
            {
                "name": f"{collection}",
                "in": "body",
                "description": f"The object to use for {collection} bulk update",
                "schema": {"type": "object"},
            }
        )
        schema_props = {"count": {"type": "integer"}}
        if klass.resource.paginate:
            schema_props["has_more"] = {"type": "boolean"}
            schema_props["total_count"] = {"type": "integer"}
            schema_props["total_pages"] = {"type": "integer"}
            params += get_limit_params(klass.resource, method_name)
        spec = {
            "summary": f"Filter and update {collection}.",
            "operationId": f"update{doc_name}s",
            "parameters": params,
            "responses": {
                200: {
                    "description": f"Number of {collection} updated",
                    "schema": {"type": "object", "properties": schema_props},
                },
                "default": default_response,
            },
        }

    elif method_name == "BulkDelete":
        params = filter_params
        schema_props = {"count": {"type": "integer"}}
        if klass.resource.paginate:
            schema_props["has_more"] = {"type": "boolean"}
            schema_props["total_count"] = {"type": "integer"}
            schema_props["total_pages"] = {"type": "integer"}
            params += get_limit_params(klass.resource, method_name)
        spec = {
            "summary": f"Filter and delete {collection}.",
            "operationId": f"delete{doc_name}s",
            "parameters": params,
            "responses": {
                200: {
                    "description": f"Number of {collection} deleted",
                    "schema": {"type": "object", "properties": schema_props},
                },
                "default": default_response,
            },
        }

    elif method_name == "Delete":
        spec = {
            "summary": f"Delete a {collection[:-1]}.",
            "operationId": f"delete{doc_name}By{id_field}",
            "parameters": [
                {
                    "name": "pk",
                    "in": "path",
                    "type": "string",
                    "required": True,
                    "description": f"The {collection[:-1]} (primary key) to delete",
                }
            ],
            "responses": {
                200: {"description": f"{collection[:-1]} deleted"},
                "default": default_response,
            },
        }

    return spec


class SwaggerView(OriginalSwaggerView, ResourceView):
    """A class-based view defining additional methods"""

    def __init_subclass__(cls, **kwargs):
        """initialize Schema, decorators, definitions, and tags"""
        super().__init_subclass__(**kwargs)

        if not __name__ == cls.__module__:
            # e.g.: cls.__module__ = mpcontribs.api.projects.views
            views_path = cls.__module__.split(".")
            doc_path = ".".join(views_path[:-1] + ["document"])
            cls.tags = [views_path[-2]]
            doc_filepath = doc_path.replace(".", os.sep) + ".py"
            if os.path.exists(doc_filepath):
                cls.doc_name = cls.tags[0].capitalize()
                Model = getattr(import_module(doc_path), cls.doc_name)
                cls.schema_name = cls.doc_name + "Schema"
                cls.Schema = type(
                    cls.schema_name,
                    (ModelSchema, object),
                    {
                        "Meta": type(
                            "Meta",
                            (object,),
                            dict(model=Model, ordered=True, model_build_obj=False),
                        )
                    },
                )
                cls.definitions = {cls.schema_name: schema2jsonschema(cls.Schema)}
                cls.resource.schema = cls.Schema

                # write flask-mongorest swagger specs
                for method in cls.methods:
                    spec = get_specs(cls, method, cls.tags[0])
                    if spec:
                        dir_path = os.path.join(DOC_DIR, cls.tags[0])
                        file_path = os.path.join(dir_path, method.__name__ + ".yml")
                        if not os.path.exists(file_path):
                            os.makedirs(dir_path, exist_ok=True)

                        if is_gunicorn:
                            with open(file_path, "w") as f:
                                yaml.dump(spec, f)
                                logger.debug(
                                    f"{cls.tags[0]}.{method.__name__} written to {file_path}"
                                )

    def get_groups(self, request):
        groups = request.headers.get("X-Authenticated-Groups", "").split(",")
        groups += request.headers.get("X-Consumer-Groups", "").split(",")
        return set(grp.strip() for grp in groups if grp)

    def is_anonymous(self, request):
        if not request.headers.get("X-Consumer-Username", ""):
            return True

        is_anonymous = request.headers.get("X-Anonymous-Consumer", False)
        if isinstance(is_anonymous, str):
            is_anonymous = False if is_anonymous == "false" else True

        return is_anonymous

    def is_external(self, request):
        return request.headers.get(
            "X-Forwarded-Host"
        ) is not None and not request.headers.get("Origin")

    def is_admin(self, groups):
        admin_group = os.environ.get("ADMIN_GROUP", "admin")
        return admin_group in groups

    def is_admin_or_project_user(self, request, obj):
        if self.is_anonymous(request):
            return False

        groups = self.get_groups(request)
        if self.is_admin(groups):
            return True

        if hasattr(obj, "owner"):
            owner = obj.owner
            project = obj.name
        elif hasattr(obj, "project"):
            owner = obj.project.owner
            project = obj.project.name
        else:
            raise Unauthorized(f"Unable to authorize {obj}")

        username = request.headers.get("X-Consumer-Username")
        return project in groups or owner == username

    def get_projects(self):
        # project is LazyReferenceFields (multiple queries)
        module = import_module("mpcontribs.api.projects.document")
        Projects = getattr(module, "Projects")
        exclude = list(Projects._fields.keys())
        only = ["name", "owner", "is_public", "is_approved"]
        return Projects.objects.exclude(*exclude).only(*only)

    def get_projects_filter(self, username, groups, filter_names=None):
        projects = self.get_projects()
        if filter_names:
            projects = projects.filter(name__in=filter_names)

        q = {"private": [], "public": []}

        for project in projects:
            if project.owner == username or project.name in groups:
                q["private"].append(project.name)
            elif project.is_public and project.is_approved:
                q["public"].append(project.name)

        # reduced query
        qfilter = Q()
        if q["private"]:
            qfilter |= Q(project__in=q["private"])
        if q["public"]:
            qfilter |= Q(project__in=q["public"], is_public=True)

        return qfilter

    def has_read_permission(self, request, qs):
        groups = self.get_groups(request)
        if self.is_admin(groups):
            return qs  # admins can read all entries

        is_anonymous = self.is_anonymous(request)
        is_external = self.is_external(request)
        username = request.headers.get("X-Consumer-Username")
        approved_public_filter = Q(is_public=True, is_approved=True)

        if request.path.startswith("/projects/"):
            # external or internal requests can both read full project info
            # anonymous requests can only read public approved projects
            if is_anonymous:
                return qs.filter(approved_public_filter)

            # authenticated requests can read approved public or accessible non-public projects
            qfilter = approved_public_filter | Q(owner=username)
            if groups:
                qfilter |= Q(name__in=list(groups))

            return qs.filter(qfilter)
        else:
            # contributions are set private/public independent from projects
            # anonymous requests:
            # - external: only meta-data of public contributions in approved public projects
            # - internal: full public contributions in approved public projects
            # authenticated requests:
            # - private contributions in a public project are only accessible to owner/group
            # - any contributions in a private project are only accessible to owner/group
            component = request.path.split("/")[1]

            if component == "contributions":
                q = qs._query
                if is_anonymous and is_external:
                    qs = qs.exclude("data")

                if q and "project" in q and isinstance(q["project"], str):
                    projects = self.get_projects()
                    try:
                        project = projects.get(name=q["project"])
                    except DoesNotExist:
                        return qs.none()

                    if project.owner == username or project.name in groups:
                        return qs
                    elif project.is_public and project.is_approved:
                        return qs.filter(is_public=True)
                    else:
                        return qs.none()
                else:
                    names = None
                    if hasattr(qs._query_obj, "children"):
                        children = deepcopy(qs._query_obj.children)
                    else:
                        children = [deepcopy(qs._query_obj)]

                    qs._query_obj = Q()
                    for node in children:
                        for field, value in node.query.items():
                            if field == "project__in":
                                names = value
                            else:
                                qs = qs.filter(**{field: value})

                    qfilter = self.get_projects_filter(
                        username, groups, filter_names=names
                    )
                    return qs.filter(qfilter)
            else:
                # get component Object IDs for queryset
                pk = request.view_args.get("pk")
                from mpcontribs.api.contributions.document import get_resource

                resource = get_resource(component)
                qfilter = lambda qs: qs.clone()

                if pk:
                    ids = [resource.get_object(pk, qfilter=qfilter).id]
                else:
                    ids = [o.id for o in resource.get_objects(qfilter=qfilter)[0]]

                if not ids:
                    return qs.none()

                # get list of readable contributions and their component Object IDs
                module = import_module("mpcontribs.api.contributions.document")
                Contributions = getattr(module, "Contributions")
                qfilter = self.get_projects_filter(username, groups)
                component = component[:-1] if component == "notebooks" else component
                qfilter &= Q(**{f"{component}__in": ids})
                contribs = (
                    Contributions.objects(qfilter).only(component).limit(len(ids))
                )
                # return new queryset using "ids__in"
                readable_ids = (
                    [getattr(contrib, component).id for contrib in contribs]
                    if component == "notebook"
                    else [
                        dbref.id
                        for contrib in contribs
                        for dbref in getattr(contrib, component)
                        if dbref.id in ids
                    ]
                )
                if not readable_ids:
                    return qs.none()

                qs._query_obj = Q(id__in=readable_ids)
                # exclude optional fields if anonymous external request
                if is_anonymous and is_external:
                    exclude = resource.get_optional_fields()
                    qs = qs.exclude(*exclude)

                return qs

    def has_add_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)

    def has_change_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)

    def has_delete_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)
