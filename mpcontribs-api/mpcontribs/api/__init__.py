import logging, os
from importlib import import_module
from flask import Flask, redirect, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
from flasgger import Swagger
from flask_json import FlaskJSON

logger = logging.getLogger('app')

def get_collections(db):
    conn = db.app.extensions['mongoengine'][db]['conn']
    return conn.mpcontribs.list_collection_names()

# http://flask.pocoo.org/snippets/77/
def get_resource_as_string(name, charset='utf-8'):
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('config.py', silent=True)
    app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string
    if app.config.get('DEBUG'):
        from flask_cors import CORS
        CORS(app) # enable for development (allow localhost)
    FlaskJSON(app)
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
