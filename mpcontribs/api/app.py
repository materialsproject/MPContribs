import logging, os
from importlib import import_module
from flask import Flask, redirect, send_from_directory
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
#from flask_pymongo import BSONObjectIdConverter
from flasgger import Swagger
from flask_json import FlaskJSON

logger = logging.getLogger('app')

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

def get_collections(db):
    conn = db.app.extensions['mongoengine'][db]['conn']
    #return conn.mpcontribs.list_collection_names() # TODO replace below
    return ['provenances']

def create_app(name):
    app = Flask(name, static_url_path='/', static_folder='docs/_build/html/')
    app.config.from_envvar('APP_CONFIG_FILE')
    FlaskJSON(app)
    Logging(app)
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
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

if __name__ == '__main__':
    app = create_app(__name__)

    @app.route('/')
    @app.route('/<path:filename>')
    def index(filename='index.html'):
        return app.send_static_file(filename)

    app.run(host='0.0.0.0')
