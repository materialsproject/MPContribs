"""Custom meta-class and MethodView for Swagger"""

import os
import logging
import yaml
from typing import Pattern
from importlib import import_module
from flask.views import MethodViewType
from flasgger.marshmallow_apispec import SwaggerView as OriginalSwaggerView
from marshmallow_mongoengine import ModelSchema
from flask_mongorest.views import ResourceView
from mongoengine.queryset.visitor import Q
from werkzeug.exceptions import Unauthorized
from mpcontribs.api.config import SWAGGER

logger = logging.getLogger('app')


def get_specs(klass, method, collection):
    method_name = method.__name__ if getattr(method, '__name__', None) is not None else method
    default_response = {
        'description': 'Error',
        'schema': {'type': 'object', 'properties': {'error': {'type': 'string'}}}
    }
    fields_param = None
    if klass.resource.fields is not None:
        fields_avail = klass.resource.fields + klass.resource.get_optional_fields() + ['_all']
        description = f'List of fields to include in response ({fields_avail}).'
        description += ' Use dot-notation for nested subfields.'
        fields_param = {
            'name': '_fields',
            'in': 'query',
            'default': klass.resource.fields,
            'type': 'array',
            'items': {'type': 'string'},
            'description': description
        }

    field_pagination_params = []
    for field, limits in klass.resource.fields_to_paginate.items():
        field_pagination_params.append({
            'name': f'{field}_page',
            'in': 'query',
            'default': 1,
            'type': 'integer',
            'description': f'page to retrieve for {field} field'
        })
        field_pagination_params.append({
            'name': f'{field}_per_page',
            'in': 'query',
            'default': limits[0],
            'maximum': limits[1],
            'type': 'integer',
            'description': f'number of items to retrieve per page for {field} field'
        })

    filter_params = []
    if getattr(klass.resource, 'filters', None) is not None:
        for k, v in klass.resource.filters.items():
            label = k.pattern if isinstance(k, Pattern) else k
            for op in v:
                filter_params.append({
                    'name': label if op.op == 'exact' else f'{label}__{op.op}',
                    'in': 'query', 'type': op.typ,
                    'description': f'filter {label}' if op.op == 'exact' else f'filter {label} via ${op.op}'
                })
                if op.typ == 'array':
                    filter_params[-1]['items'] = {'type': 'string'}

    spec = None
    if method_name == 'Fetch':
        params = [{
            'name': 'pk',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': f'{collection[:-1]} (primary key)'
        }]
        if fields_param is not None:
            params.append(fields_param)
        if field_pagination_params:
            params += field_pagination_params
        spec = {
            'summary': f'Retrieve a {collection[:-1]}.',
            'operationId': 'get_entry',
            'parameters': params,
            'responses': {
                200: {
                    'description': f'single {collection} entry',
                    'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                }, 'default': default_response
            }
        }
    elif method_name == 'List':
        params = [fields_param] if fields_param is not None else []
        if field_pagination_params:
            params += field_pagination_params

        if klass.resource.allowed_ordering:
            allowed_ordering = [
                o.pattern if isinstance(o, Pattern) else o
                for o in klass.resource.allowed_ordering
            ]
            params.append({
                'name': '_order_by',
                'in': 'query',
                'type': 'string',
                'description': f'order {collection} via {allowed_ordering}'
            })

        if filter_params:
            params += filter_params

        schema_props = {
            'data': {
                'type': 'array',
                'items': {'$ref': f'#/definitions/{klass.schema_name}'}
            }
        }
        if klass.resource.paginate:
            schema_props['has_more'] = {'type': 'boolean'}
            schema_props['total_count'] = {'type': 'integer'}
            schema_props['total_pages'] = {'type': 'integer'}
            params.append({
                'name': '_skip',
                'in': 'query',
                'type': 'integer',
                'description': 'number of items to skip'
            })
            params.append({
                'name': '_limit',
                'in': 'query',
                'type': 'integer',
                'description': 'maximum number of items to return'
            })
            params.append({
                'name': 'page',
                'in': 'query',
                'type': 'integer',
                'description': 'page number to return (in batches of `per_page/_limit`; alternative to `_skip`)'
            })
            params.append({
                'name': 'per_page',
                'in': 'query',
                'type': 'integer',
                'description': 'maximum number of items to return per page (same as `_limit`)'
            })

        spec = {
            'summary': f'Retrieve and filter {collection}.',
            'operationId': 'get_entries',
            'parameters': params,
            'responses': {
                200: {
                    'description': f'list of {collection}',
                    'schema': {
                        'type': 'object',
                        'properties': schema_props
                    }
                }, 'default': default_response
            }
        }
    elif method_name == 'Create':
        spec = {
            'summary': f'Create a new {collection[:-1]}.',
            'operationId': 'create_entry',
            'parameters': [{
                'name': f'{collection[:-1]}',
                'in': 'body',
                'description': f'The object to use for {collection[:-1]} creation',
                'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
            }],
            'responses': {
                200: {
                    'description': f'{collection[:-1]} created',
                    'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                }, 'default': default_response
            }
        }
    elif method_name == 'Update':
        spec = {
            'summary': f'Update a {collection[:-1]}.',
            'operationId': 'update_entry',
            'parameters': [{
                'name': 'pk',
                'in': 'path',
                'type': 'string',
                'required': True,
                'description': f'The {collection[:-1]} (primary key) to update'
            }, {
                'name': f'{collection[:-1]}',
                'in': 'body',
                'description': f'The object to use for {collection[:-1]} update',
                'schema': {'type': 'object'}
            }],
            'responses': {
                200: {
                    'description': f'{collection[:-1]} updated',
                    'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                }, 'default': default_response
            }
        }
    elif method_name == 'BulkUpdate':
        params = filter_params if filter_params else []
        params.append({
            'name': f'{collection}',
            'in': 'body',
            'description': f'The object to use for {collection} bulk update',
            'schema': {'type': 'object'}
        })

        spec = {
            'summary': f'Update {collection} in bulk.',
            'operationId': 'update_entries',
            'parameters': params,
            'responses': {
                200: {
                    'description': f'Number of {collection} updated',
                    'schema': {
                        'type': 'object',
                        'properties': {'count': {'type': 'integer'}}
                    }
                }, 'default': default_response
            }
        }
    elif method_name == 'Delete':
        spec = {
            'summary': f'Delete a {collection[:-1]}.',
            'operationId': 'delete_entry',
            'parameters': [{
                'name': 'pk',
                'in': 'path',
                'type': 'string',
                'required': True,
                'description': f'The {collection[:-1]} (primary key) to delete'
            }],
            'responses': {
                200: {'description': f'{collection[:-1]} deleted'},
                'default': default_response
            }
        }

    return spec


# https://github.com/pallets/flask/blob/master/flask/views.py
class SwaggerViewType(MethodViewType):
    """Metaclass for `SwaggerView` defining custom attributes"""

    def __init__(cls, name, bases, d):
        """initialize Schema, decorators, definitions, and tags"""
        super(SwaggerViewType, cls).__init__(name, bases, d)

        if not __name__ == cls.__module__:
            # e.g.: cls.__module__ = mpcontribs.api.projects.views
            views_path = cls.__module__.split('.')
            doc_path = '.'.join(views_path[:-1] + ['document'])
            cls.tags = [views_path[-2]]
            doc_filepath = doc_path.replace('.', os.sep) + '.py'
            if os.path.exists(doc_filepath):
                cls.doc_name = cls.tags[0].capitalize()
                Model = getattr(import_module(doc_path), cls.doc_name)
                cls.schema_name = cls.doc_name + 'Schema'
                cls.Schema = type(cls.schema_name, (ModelSchema, object), {
                    'Meta': type('Meta', (object,), dict(
                        model=Model, ordered=True, model_build_obj=False
                    ))
                })
                cls.definitions = {cls.schema_name: cls.Schema}
                cls.resource.schema = cls.Schema

                # write flask-mongorest swagger specs
                for method in cls.methods:
                    spec = get_specs(cls, method, cls.tags[0])
                    if spec:
                        dir_path = os.path.join(SWAGGER["doc_dir"], cls.tags[0])
                        if not os.path.exists(dir_path):
                            os.makedirs(dir_path)

                        file_path = os.path.join(dir_path, method.__name__ + '.yml')
                        with open(file_path, 'w') as f:
                            yaml.dump(spec, f)


class SwaggerView(OriginalSwaggerView, ResourceView, metaclass=SwaggerViewType):
    """A class-based view defining additional methods"""

    def get_groups(self, request):
        groups = request.headers.get('X-Consumer-Groups')
        return [] if groups is None else groups.split(',')

    def is_admin_or_project_user(self, request, obj):
        groups = self.get_groups(request)
        is_approved = obj.is_approved if hasattr(obj, 'is_approved') else obj.project.is_approved
        owner = obj.owner if hasattr(obj, 'owner') else obj.project.owner
        project = obj.project.id if hasattr(obj.project, 'id') else obj.project
        username = request.headers.get('X-Consumer-Username')
        return 'admin' in groups or (
            (project in groups or owner == username) and is_approved
        )

    def has_read_permission(self, request, qs):
        groups = self.get_groups(request)
        if 'admin' in groups:
            return qs  # admins can read all entries
        # only read public or approved project entries
        username = request.headers.get('X-Consumer-Username')
        qfilter = Q(is_public=True)
        if groups:
            qfilter |= Q(project__in=groups, is_approved=True)
        if username:
            qfilter |= Q(owner=username, is_approved=True)

        if request.path.startswith('/projects/'):
            return qs.filter(qfilter)

        # project is LazyReferenceField
        module = import_module('mpcontribs.api.projects.document')
        Model = getattr(module, 'Projects')
        projects = Model.objects.only('project').filter(qfilter)
        qfilter = Q(is_public=True) | Q(project__in=projects)
        return qs.filter(qfilter)

    def has_add_permission(self, request, obj):
        if not self.is_admin_or_project_user(request, obj):
            return False

        if hasattr(obj, 'identifier'):
            # TODO add unique_identifiers field in Projects to disable duplicate check
            nobjs = self.resource.document.objects(
                project=obj.project.id, identifier=obj.identifier
            ).count()
            if nobjs > 0:
                raise Unauthorized(f'{obj.identifier} already added for {obj.project.id}')

        return True

    def has_change_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)

    def has_delete_permission(self, request, obj):
        return self.is_admin_or_project_user(request, obj)
