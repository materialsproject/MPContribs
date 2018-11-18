import re
from flask import Flask
from flask_rebar import Rebar, SwaggerV2Generator
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
#from flask_pymongo import BSONObjectIdConverter
from mpcontribs.api.registry import setup_registry

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

def create_app(name):
    rebar = Rebar()
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    log = Logging(app)
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    conn = app.extensions['mongoengine'][db]['conn']
    registry = setup_registry(conn)
    rebar.add_handler_registry(registry)
    rebar.init_app(app)
    return app

if __name__ == '__main__':
    create_app(__name__).run()
