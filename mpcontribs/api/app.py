import re
from decorator import decorator
from requests import get
from flask import Flask
from flask import current_app, request
from flask_rebar import Rebar, errors, SwaggerV2Generator
from flask_mongoengine import MongoEngine
from flask_marshmallow import Marshmallow
from mpcontribs.api.registry import registry

@decorator
def api_check(f, *args, **kw):
    # TODO SSL check?
    api_key = request.headers.get('X-API-KEY')
    if not api_key:
        errors.Forbidden("X-API-KEY not supplied.")
    if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
        errors.Forbidden("X-API-KEY wrong format.")
    api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
    if not api_check_endpoint:
        errors.InternalError('API_CHECK_ENDPOINT not set!')
    headers = {'X-API-KEY': api_key}
    api_check_response = get(api_check_endpoint, headers=headers).json()
    if not api_check_response['api_key_valid']:
        errors.Forbidden("API_KEY is not a valid key.")
    return f(*args, **kw)

#registry.handles('/<ObjectId:cid>')

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
    #from flask_pymongo import BSONObjectIdConverter
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    rebar.add_handler_registry(registry)
    rebar.init_app(app)
    return app

if __name__ == '__main__':
    create_app(__name__).run()
