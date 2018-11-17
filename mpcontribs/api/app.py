import re
from flask import Flask
from flask_rebar import Rebar, SwaggerV2Generator
from flask_mongoengine import MongoEngine
from flask_marshmallow import Marshmallow
#from flask_pymongo import BSONObjectIdConverter
from mpcontribs.api.registry import registry

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

#authorizations = { 'apikey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-KEY'} }
#ordered=True, version='1.0', title='MPContribs API',
#description='API for contributed Materials Project data',
#authorizations=authorizations, security='apikey', contact='phuck@lbl.gov',

def create_app(name):
    rebar = Rebar()
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    rebar.add_handler_registry(registry)
    rebar.init_app(app)
    return app

if __name__ == '__main__':
    create_app(__name__).run()
