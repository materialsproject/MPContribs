import re
from flask import Flask, jsonify
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
#from flask_pymongo import BSONObjectIdConverter
#from mpcontribs.api.registry import setup_registry
from flasgger import Swagger

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

def create_app(name):
    #rebar = Rebar()
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    #app.config['SWAGGER'] = { 'title': 'My API' } # TODO
    log = Logging(app)
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    swagger = Swagger(app, parse=True)
    from mpcontribs.api.provenances import provenances
    #conn = app.extensions['mongoengine'][db]['conn']
    #registry = setup_registry(conn)
    app.register_blueprint(provenances, url_prefix='/provenances')
    return app

if __name__ == '__main__':
    create_app(__name__).run()
