import logging
from importlib import import_module
from flask import Flask
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
#from flask_pymongo import BSONObjectIdConverter
from flasgger import Swagger

logger = logging.getLogger('app')

def get_collections(db):
    conn = db.app.extensions['mongoengine'][db]['conn']
    #return conn.mpcontribs.list_collection_names() # TODO replace below
    return ['provenances']

def create_app(name):
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    log = Logging(app)
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    swagger = Swagger(app, template=app.config.get('TEMPLATE'))
    collections = get_collections(db)
    for collection in collections:
        module_path = '.'.join(['mpcontribs', 'api', collection])
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
