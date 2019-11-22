"""Flask App for MPContribs API"""

import os
import logging
import yaml
from importlib import import_module
# from bson.decimal128 import Decimal128
from flask import Flask, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_mongorest import register_class
from flask_log import Logging
from flasgger import Swagger
from pandas.io.json.normalize import nested_to_record
from typing import Any, Dict

for mod in ['matplotlib', 'toronado.cssutils', 'selenium.webdriver.remote.remote_connection']:
    log = logging.getLogger(mod)
    log.setLevel('INFO')

logger = logging.getLogger('app')


def get_collections(db):
    """get list of collections in DB"""
    conn = db.app.extensions['mongoengine'][db]['conn']
    dbname = db.app.config.get('MPCONTRIBS_DB')
    return conn[dbname].list_collection_names()


def get_resource_as_string(name, charset='utf-8'):
    """http://flask.pocoo.org/snippets/77/"""
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)


# utility to use in views
def construct_query(filters):
    """constructs a mongoengine query from a list of filters

    example:
        C__gte:0.42,C__lte:2.10,ΔE-QP.direct__lte:11.3
        -> content__data__C__value__lte
    """
    query = {}
    for f in filters:
        if '__' in f and ':' in f:
            k, v = f.split(':')
            col, op = k.rsplit('__', 1)
            col = col.replace(".", "__")
            try:
                val = float(v)
                key = f'content__data__{col}__value__{op}'
                query[key] = val
            except ValueError:
                key = f'content__data__{col}__{op}'
                query[key] = v
    return query


# https://stackoverflow.com/a/55545369
def unflatten(
    d: Dict[str, Any],
    base: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Convert any keys containing dotted paths to nested dicts

    >>> unflatten({'a': 12, 'b': 13, 'c': 14})  # no expansion
    {'a': 12, 'b': 13, 'c': 14}

    >>> unflatten({'a.b.c': 12})  # dotted path expansion
    {'a': {'b': {'c': 12}}}

    >>> unflatten({'a.b.c': 12, 'a': {'b.d': 13}})  # merging
    {'a': {'b': {'c': 12, 'd': 13}}}

    >>> unflatten({'a.b': 12, 'a': {'b': 13}})  # insertion-order overwrites
    {'a': {'b': 13}}

    >>> unflatten({'a': {}})  # insertion-order overwrites
    {'a': {}}
    """
    if base is None:
        base = {}

    for key, value in d.items():
        root = base

        ###
        # If a dotted path is encountered, create nested dicts for all but
        # the last level, then change root to that last level, and key to
        # the final key in the path. This allows one final setitem at the bottom
        # of the loop.
        if '.' in key:
            *parts, key = key.split('.')

            for part in parts:
                root.setdefault(part, {})
                root = root[part]

        if isinstance(value, dict):
            value = unflatten(value, root.get(key, {}))

        root[key] = value

    return base


def get_cleaned_data(data):
    return dict(
        (k.rsplit('.', 1)[0] if k.endswith('.display') else k, v)
        for k, v in nested_to_record(data, sep='.').items()
        if not k.endswith('.value') and not k.endswith('.unit')
    )



def create_app():
    """create flask app"""
    app = Flask(__name__)
    app.config.from_pyfile('config.py', silent=True)
    app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string
    if app.config.get('DEBUG'):
        from flask_cors import CORS
        CORS(app)  # enable for development (allow localhost)

    # json = FlaskJSON(app)

    # @json.encoder
    # def custom_encoder(o):
    #     if isinstance(o, Decimal128):
    #         return float(o.to_decimal())

    Logging(app)
    Marshmallow(app)
    db = MongoEngine(app)
    Swagger(app, template=app.config.get('TEMPLATE'))
    collections = get_collections(db)

    for collection in collections:
        module_path = '.'.join(['mpcontribs', 'api', collection, 'views'])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as ex:
            logger.warning(f'API module {module_path}: {ex}')
            continue

        # try:
        blueprint = getattr(module, collection)
        app.register_blueprint(blueprint, url_prefix='/'+collection)
        klass = getattr(module, collection.capitalize() + 'View')
        register_class(app, klass, name=collection)

        # add schema and specs for flask-mongorest views
        if getattr(klass, 'resource', None) is not None:
            klass.resource.schema = klass.Schema

            dir_path = os.path.join(app.config["SWAGGER"]["doc_dir"], collection)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            for method in klass.methods:
                file_path = os.path.join(dir_path, method.__name__ + '.yml')
                fields_param = None
                if klass.resource.fields is not None:
                    fields_avail = klass.resource.fields + klass.resource.get_optional_fields() + ['_all']
                    fields_param = {
                        'name': '_fields',
                        'in': 'query',
                        'default': klass.resource.fields,
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'List of fields to include in response. Use dot-notation for nested subfields.'
                    }

                spec = None
                if method.__name__ == 'Fetch':
                    params = [{
                        'name': 'pk',
                        'in': 'path',
                        'type': 'string',
                        'required': True,
                        'description': f'{collection[:-1]} (primary key)'
                    }]
                    if fields_param is not None:
                        params.append(fields_param)
                    spec = {
                        'summary': f'Retrieve a {collection[:-1]}.',
                        'operationId': 'get_entry',
                        'parameters': params,
                        'responses': {
                            200: {
                                'description': f'single {collection} entry',
                                'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                            }
                        }
                    }
                elif method.__name__ == 'List':
                    params = [fields_param] if fields_param is not None else []

                    if klass.resource.allowed_ordering:
                        params.append({
                            'name': '_order_by',
                            'in': 'query',
                            'type': 'string',
                            'enum': klass.resource.allowed_ordering,
                            'description': f'order {collection}'
                        })

                    if klass.resource.filters:
                        params += [{
                            'name': k if op.op == 'exact' else f'{k}__{op.op}',
                            'in': 'query',
                            'type': 'string',
                            'description': f'filter {k}' if op.op == 'exact' else f'filter {k} via ${op.op}'
                        } for k, v in klass.resource.filters.items() for op in v]

                    schema_props = {
                        'data': {
                            'type': 'array',
                            'items': {'$ref': f'#/definitions/{klass.schema_name}'}
                        }
                    }
                    if klass.resource.paginate:
                        schema_props['has_more'] = {'type': 'boolean'}
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
                            }
                        }
                    }
                elif method.__name__ == 'Create':
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
                            }
                        }
                    }
                elif method.__name__ == 'Update':
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
                            'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                        }],
                        'responses': {
                            200: {
                                'description': f'{collection[:-1]} updated',
                                'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                            }
                        }
                    }
                elif method.__name__ == 'BulkUpdate':
                    spec = {
                        'summary': f'Update {collection} in bulk.',
                        'operationId': 'update_entries',
                        'parameters': [{
                            'name': f'{collection}',
                            'in': 'body',
                            'description': f'The object to use for {collection} bulk update',
                            'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                        }],
                        'responses': {
                            200: {
                                'description': f'Number of {collection} updated',
                                'schema': {
                                    'type': 'object',
                                    'properties': {'count': {'type': 'integer'}}
                                }
                            }
                        }
                    }
                elif method.__name__ == 'Delete':
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
                            200: {'description': f'{collection[:-1]} deleted'}
                        }
                    }

                if spec:
                    with open(file_path, 'w') as f:
                        yaml.dump(spec, f)

        # except AttributeError as ex:
        #     logger.warning('Failed to register {}: {}'.format(
        #         module_path, collection, ex
        #     ))

    return app
