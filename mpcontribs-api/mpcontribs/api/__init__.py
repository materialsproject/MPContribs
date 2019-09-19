import logging, os, yaml
from importlib import import_module
from bson.decimal128 import Decimal128
from flask import Flask, redirect, current_app
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
    conn = db.app.extensions['mongoengine'][db]['conn']
    return conn.mpcontribs.list_collection_names()

# http://flask.pocoo.org/snippets/77/
def get_resource_as_string(name, charset='utf-8'):
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)

# utility to use in views
def construct_query(filters):
    # C__gte:0.42,C__lte:2.10,ΔE-QP.direct__lte:11.3
    # -> content__data__C__value__lte
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
            except:
                key = f'content__data__{col}__{op}'
                query[key] = v
    return query

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('config.py', silent=True)
    app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string
    if app.config.get('DEBUG'):
        from flask_cors import CORS
        CORS(app) # enable for development (allow localhost)

    #json = FlaskJSON(app)

    #@json.encoder
    #def custom_encoder(o):
    #    if isinstance(o, Decimal128):
    #        return float(o.to_decimal())

    Logging(app)
    Marshmallow(app)
    db = MongoEngine(app)
    swagger = Swagger(app, template=app.config.get('TEMPLATE'))
    collections = get_collections(db)

    for collection in collections:
        module_path = '.'.join(['mpcontribs', 'api', collection, 'views'])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as ex:
            logger.warning(f'API module {module_path}: {ex}')
            continue

        #try:
        blueprint = getattr(module, collection)
        app.register_blueprint(blueprint, url_prefix='/'+collection)
        klass = getattr(module, collection.capitalize() + 'View')
        register_class(app, klass, name=collection)

        # add schema and specs for flask-mongorest views
        if getattr(klass, 'resource', None) is not None:
            klass.resource.schema = klass.Schema

            for rule in app.url_map.iter_rules():
                endpoint = app.view_functions[rule.endpoint]
                endpoint.view_class = klass
                if collection in rule.endpoint:
                    for verb in rule.methods.difference(('HEAD', 'OPTIONS')):
                        print(rule, rule.endpoint, verb)
                        key = "{}_{}".format(rule.endpoint, verb.lower())
                        if key == f'{collection}_get':
                            spec = { # FETCH
                                'operationId': 'get_entry',
                                'parameters': [{
                                    'name': 'pk',
                                    'in': 'path',
                                    'type': 'string',
                                    'description': f'primary key for {klass.doc_name[:-1]}'
                                }],
                                'responses': {
                                    200: {
                                        'description': f'single {klass.doc_name} entry',
                                        'schema': {'$ref': f'#/definitions/{klass.schema_name}'}
                                    }
                                }
                            }
                        else:
                            spec = {}

                        with open(f'{app.config["SWAGGER"]["doc_dir"]}/{key}.yml', 'w') as f:
                            yaml.dump(spec, f)

        #except AttributeError as ex:
        #    logger.warning('Failed to register {}: {}'.format(
        #        module_path, collection, ex
        #    ))

    return app



            #if m.__name__ == 'List':
            #    method.specs_dict = {
            #        'operationId': 'get_entries',
            #        'parameters': [{
            #            'name': '_fields',
            #            'in': 'query',
            #            'type': 'array',
            #            'items': {'type': 'string'},
            #            'description': 'list of fields to include in response'
            #        }, {
            #            'name': '_order_by',
            #            'in': 'query',
            #            'type': 'string',
            #            'description': 'field by which to order response'
            #        }], # TODO _skip and _limit: utilize the built-in functions of mongodb
            #        'responses': {
            #            '200': {
            #                'description': f'list of {doc_name}',
            #                'schema': {
            #                    'type': 'array',
            #                    'items': {'$ref': f'#/definitions/{schema_name}'}
            #                }
            #            }
            #        }
            #    }
            #    for fld, ops in cls.resource.filters.items():
            #        for op in ops:
            #            method.specs_dict['parameters'].append({
            #                'name': f'{fld}__{op.op}',
            #                'in': 'query',
            #                'type': 'string',
            #                'description': f'filter {fld} by {op.op}'
            #            })
