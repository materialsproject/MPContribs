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
                fields_param = {
                    'name': '_fields',
                    'in': 'query',
                    'default': klass.resource.fields,
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': klass.resource.fields + klass.resource.get_optional_fields() + ['_all']
                    },
                    'description': 'list of fields to include in response'
                }

                spec = None
                if method.__name__ == 'Fetch':
                    spec = {
                        'summary': f'Retrieve a {collection[:-1]}.',
                        'operationId': 'get_entry',
                        'parameters': [{
                            'name': 'pk',
                            'in': 'path',
                            'type': 'string',
                            'description': f'{collection[:-1]} (primary key)'
                        }, fields_param],
                        'responses': {
                            200: {
                                'description': f'single {collection} entry',
                                'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                            }
                        }
                    }
                elif method.__name__ == 'List':
                    filter_params = [{
                        'name': f'{k}__{op.op}',
                        'in': 'query',
                        'type': 'string',
                        'description': f'filter {k} via ${op.op}'
                    } for k, v in klass.resource.filters.items() for op in v]
                    spec = {
                        'summary': f'Retrieve and filter {collection}.',
                        'operationId': 'get_entries',
                        'parameters': [fields_param, {
                            'name': '_order_by',
                            'in': 'query',
                            'type': 'string',
                            'enum': klass.resource.allowed_ordering,
                            'description': f'order {collection}'
                        }] + filter_params,
                        'responses': {
                            200: {
                                'description': f'list of {collection}',
                                'schema': {
                                    'type': 'object',
                                    'properties': {
                                        'data': {
                                            'type': 'array',
                                            'items': {'$ref': f'#/definitions/{klass.schema_name}'}
                                        }
                                    }
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
                            'description': f'The {collection[:-1]} (primary key) to update',
                            'type': 'string'
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
                            'description': f'The {collection[:-1]} (primary key) to delete',
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
