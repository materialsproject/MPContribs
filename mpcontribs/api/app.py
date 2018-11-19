import re
from flask import Flask, jsonify, redirect
from flask import request, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_log import Logging
#from flask_pymongo import BSONObjectIdConverter
from flasgger import Swagger

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

#from flask_rebar.authenticators.base import Authenticator
#swaggen.authenticator_converters = { # reset default
#    HeaderApiKeyAuthenticator: _convert_header_api_key_authenticator
#}
#registry.set_default_authenticator(authenticator)


#authenticator = HeaderApiKeyAuthenticator('X-API-KEY', 'MAPI_KEY')
#class HeaderApiKeyAuthenticator(Authenticator):
#    def __init__(self, header, name):
#        self.header = header
#        self.name = name
#
#    # TODO SSL check?
#    def authenticate(self):
#        if self.header not in request.headers:
#            raise errors.Unauthorized(messages.missing_auth_token)
#        api_key = request.headers[self.header]
#        if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
#            raise errors.Unauthorized(messages.invalid_auth_token)
#        api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
#        if not api_check_endpoint:
#            raise errors.InternalError('API_CHECK_ENDPOINT not set!')
#        headers = {self.header: api_key}
#        api_check_response = get(api_check_endpoint, headers=headers).json()
#        if not api_check_response['api_key_valid']:
#            raise errors.Unauthorized(messages.invalid_auth_token)

def create_app(name):
    app = Flask(name)
    app.config.from_envvar('APP_CONFIG_FILE')
    log = Logging(app)
    #app.url_map.converters["ObjectId"] = BSONObjectIdConverter
    ma = Marshmallow(app)
    db = MongoEngine(app)
    swagger = Swagger(app)
    #conn = app.extensions['mongoengine'][db]['conn']
    #api_pkg_path = __name__.split('.')[:-1]
    #db_name = api_pkg_path[0]
    ##collections = conn[db_name].list_collection_names() # TODO replace below
    #collections = ['contributions', 'provenances']
    #for collection in collections:
    #    module_path = '.'.join(api_pkg_path + [collection])

    #    try:
    #        module = import_module(module_path)
    #    except ModuleNotFoundError:
    #        logger.warning('API module {} not found!'.format(module_path))
    #        continue
    from mpcontribs.api.provenances import provenances
    app.register_blueprint(provenances, url_prefix='/provenances')
    return app

if __name__ == '__main__':
    app = create_app(__name__)

    @app.route("/")
    def index():
        return redirect("/apidocs")

    app.run()
