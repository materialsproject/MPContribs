import logging, os
from importlib import import_module
from bson.decimal128 import Decimal128
from flask import Flask, redirect, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
from flasgger import Swagger
from flask_json import FlaskJSON

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

    json = FlaskJSON(app)

    @json.encoder
    def custom_encoder(o):
        if isinstance(o, Decimal128):
            return float(o.to_decimal())

    Logging(app)
    Marshmallow(app)
    db = MongoEngine(app)
    swagger = Swagger(app, template=app.config.get('TEMPLATE'))
    collections = get_collections(db)

    for collection in collections:
        module_path = '.'.join(['mpcontribs', 'api', collection, 'views'])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError:
            logger.warning('API module {} not found!'.format(module_path))
            continue
        try:
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix='/'+collection)
        except AttributeError as ex:
            logger.warning('Failed to register blueprint {}: {}'.format(
                module_path, collection, ex
            ))

    return app
