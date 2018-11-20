from flask import redirect
from mpcontribs.api.core import create_app

#def projection(self):
#    mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
#    return None if '*' in mask.keys() else mask

#from flask_rebar.authenticators.base import Authenticator
#swaggen.authenticator_converters = { # reset default
#    HeaderApiKeyAuthenticator: _convert_header_api_key_authenticator
#}
#registry.set_default_authenticator(authenticator)

#from flask import request, current_app
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

if __name__ == '__main__':
    app = create_app(__name__)

    @app.route("/")
    def index():
        return redirect("/apidocs")

    app.run()
