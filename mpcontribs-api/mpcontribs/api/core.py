# -*- coding: utf-8 -*-
"""Custom meta-class and MethodView for Swagger"""

import os
import logging
import yaml
from flask import current_app
from typing import Pattern
from importlib import import_module
from flask.views import MethodViewType
from flasgger.marshmallow_apispec import SwaggerView as OriginalSwaggerView
from flasgger.marshmallow_apispec import schema2jsonschema
from marshmallow_mongoengine import ModelSchema
from flask_mongorest.views import ResourceView
from mongoengine.queryset.visitor import Q
from werkzeug.exceptions import Unauthorized
from mpcontribs.api.config import SWAGGER

logger = logging.getLogger("app")


def get_specs(klass, method, collection):
    method_name = (
        method.__name__ if getattr(method, "__name__", None) is not None else method
    )
    default_response = {
        "description": "Error",
        "schema": {"type": "object", "properties": {"error": {"type": "string"}}},
    }
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

    limit_params = [
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
            "description": "maximum number of items to return per page (same as `_limit`)",
        },
    ]

    filter_params = []
    if getattr(klass.resource, "filters", None) is not None:
        for k, v in klass.resource.filters.items():
            label = k.pattern if isinstance(k, Pattern) else k
            for op in v:
                filter_params.append(
                    {
                        "name": label if op.op == "exact" else f"{label}__{op.op}",
                        "in": "query",
                        "type": op.typ,
                        "description": f"filter {label}"
                        if op.op == "exact"
                        else f"filter {label} via ${op.op}",
                    }
                )
                if op.typ == "array":
                    filter_params[-1]["items"] = {"type": "string"}

    order_params = []
    if klass.resource.allowed_ordering:
        allowed_ordering = [
            o.pattern if isinstance(o, Pattern) else o
            for o in klass.resource.allowed_ordering
        ]
        order_params = [
            {
                "name": "_order_by",
                "in": "query",
                "type": "string",
                "description": f"order {collection} via {allowed_ordering}",
            },
            {
                "name": "order",
                "in": "query",
                "type": "string",
                "description": f"order {collection} *asc* or *desc*",
            },
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
            "operationId": "get_entry",
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
            params += limit_params
        spec = {
            "summary": f"Filter and retrieve {collection}.",
            "operationId": "get_entries",
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
                "description": f"MIME Download Type: gz",
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
        spec = {
            "summary": f"Filter and download {collection}.",
            "operationId": "download_entries",
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
            "operationId": "create_entry",
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
            "operationId": "create_entries",
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
            "operationId": "update_entry",
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
            params += limit_params
        spec = {
            "summary": f"Filter and update {collection}.",
            "operationId": "update_entries",
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
            params += limit_params
        spec = {
            "summary": f"Filter and delete {collection}.",
            "operationId": "delete_entries",
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
            "operationId": "delete_entry",
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


# https://github.com/pallets/flask/blob/master/flask/views.py
# TODO FYI https://github.com/flasgger/flasgger/pull/396
class SwaggerViewType(MethodViewType):
    """Metaclass for `SwaggerView` defining custom attributes"""

    def __init__(cls, name, bases, d):
        """initialize Schema, decorators, definitions, and tags"""
        super(SwaggerViewType, cls).__init__(name, bases, d)

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
                        dir_path = os.path.join(SWAGGER["doc_dir"], cls.tags[0])
                        file_path = os.path.join(dir_path, method.__name__ + ".yml")
                        if not os.path.exists(file_path):
                            os.makedirs(dir_path, exist_ok=True)
                            with open(file_path, "w") as f:
                                yaml.dump(spec, f)
                                logger.warning(
                                    f"{cls.tags[0]}.{method.__name__} written to {file_path}"
                                )


class SwaggerView(OriginalSwaggerView, ResourceView, metaclass=SwaggerViewType):
    """A class-based view defining additional methods"""

    def get_groups(self, request):
        groups = request.headers.get("X-Authenticated-Groups", "").split(",")
        groups += request.headers.get("X-Consumer-Groups", "").split(",")
        return set(g for g in groups if g)

    def is_anonymous(self, request):
        if not request.headers.get("X-Consumer-Username", ""):
            return True

        return request.headers.get("X-Anonymous-Consumer", False)

    def is_admin(self, groups):
        cname = current_app.config["PORTAL_CNAME"]
        return "admin" in groups or f"admin_{cname}" in groups

    def is_admin_or_project_user(self, request, obj):
        if self.is_anonymous(request):
            return False

        groups = self.get_groups(request)
        if self.is_admin(groups):
            return True

        if hasattr(obj, "is_approved"):
            is_approved = obj.is_approved
            owner = obj.owner
            project = obj.name
        elif hasattr(obj, "project"):
            is_approved = obj.project.is_approved
            owner = obj.project.owner
            project = obj.project.name
        else:
            raise Unauthorized(f"Unable to authorize {obj}")

        username = request.headers.get("X-Consumer-Username")
        return (project in groups or owner == username) and is_approved

    def has_read_permission(self, request, qs):
        groups = self.get_groups(request)
        if self.is_admin(groups):
            return qs  # admins can read all entries

        if self.is_anonymous(request):
            # anonymous can only read public approved projects (no contributions)
            if not request.path.startswith("/projects/"):
                return qs.none()

            return qs.filter(is_public=True, is_approved=True)

        username = request.headers.get("X-Consumer-Username")

        if request.path.startswith("/projects/"):
            # all public and non-public but accessible projects
            qfilter = Q(is_public=True) | Q(owner=username)
            if groups:
                qfilter |= Q(name__in=list(groups))

            return qs.filter(Q(is_approved=True) & qfilter)

        elif request.path.startswith("/contributions/"):
            # project is LazyReferenceFields (multiple queries)
            module = import_module("mpcontribs.api.projects.document")
            Projects = getattr(module, "Projects")
            projects = Projects.objects.only("name", "owner", "is_public", "is_approved")

            # contributions are set private/public independent from projects
            # - private contributions in a public project are only accessible to owner/group
            # - any contributions in a private project are only accessible to owner/group
            q = qs._query
            if "project" in q and isinstance(q["project"], str):
                project = projects.get(name=q["project"])
                if not project.is_approved:
                    return qs.none()

                if project.owner == username or project.name in groups:
                    return qs
                elif project.is_public:
                    return qs.filter(is_public=True)
                else:
                    return qs.none()

            else:
                qfilter = Q()  # reduced query
                if "project" in q and "$in" in q["project"]:
                    names = q.pop("project").pop("$in")
                    projects = projects.filter(name__in=names)

                for project in projects:
                    if not project.is_approved:
                        continue

                    if project.owner == username or project.name in groups:
                        qfilter |= Q(project=project.name)
                    elif project.is_public:
                        qfilter |= Q(project=project.name, is_public=True)

                return qs.filter(qfilter)

        # Allowing any non-anonymous user access to endpoints for tables/structures/notebooks.
        # These components can thus technically be accessed without permission for the according
        # contribution. However, this would require knowledge of the respective ObjectIds which are
        # not knowable without access to the contribution (security by obscurity). This could be
        # considered a feature for people who'd want to share public links with collaborators.
        return qs

    def has_add_permission(self, request, obj):
        if not self.is_admin_or_project_user(request, obj):
            return False

        if hasattr(obj, "identifier") and obj.project.unique_identifiers:
            if self.resource.document.objects(
                project=obj.project.id, identifier=obj.identifier
            ).count():
                raise Unauthorized(
                    f"{obj.identifier} already added for {obj.project.id}"
                )

        return True

    def has_change_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)

    def has_delete_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)
