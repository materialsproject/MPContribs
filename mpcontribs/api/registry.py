import re
from requests import get
from marshmallow_mongoengine import fields
from flask import request, current_app
from flask_rebar import HandlerRegistry, errors, messages
from flask_rebar.authenticators.base import Authenticator
from flask_rebar.swagger_generation.swagger_generator import \
        SwaggerV2Generator, _convert_header_api_key_authenticator
from flask_rebar.swagger_generation.marshmallow_to_swagger import \
        response_converter_registry, StringConverter

from mpcontribs.api.config import VERSION
from mpcontribs.api import provenance

class ObjectIdConverter(StringConverter):
    MARSHMALLOW_TYPE = fields.ObjectId

class HeaderApiKeyAuthenticator(Authenticator):
    def __init__(self, header, name):
        self.header = header
        self.name = name

    # TODO SSL check?
    def authenticate(self):
        if self.header not in request.headers:
            raise errors.Unauthorized(messages.missing_auth_token)
        api_key = request.headers[self.header]
        if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
            raise errors.Unauthorized(messages.invalid_auth_token)
        api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
        if not api_check_endpoint:
            raise errors.InternalError('API_CHECK_ENDPOINT not set!')
        headers = {self.header: api_key}
        api_check_response = get(api_check_endpoint, headers=headers).json()
        if not api_check_response['api_key_valid']:
            raise errors.Unauthorized(messages.invalid_auth_token)


swaggen = SwaggerV2Generator(
    title='MPContribs API', version=VERSION,
    description='Operations to retrieve materials data contributed to MP'
)
swaggen.authenticator_converters = { # reset default
    HeaderApiKeyAuthenticator: _convert_header_api_key_authenticator
}

registry = HandlerRegistry(prefix=VERSION, swagger_generator=swaggen)
authenticator = HeaderApiKeyAuthenticator('X-API-KEY', 'apiKey')
registry.set_default_authenticator(authenticator)
response_converter_registry.register_type(ObjectIdConverter())
provenance.add_all_handlers(registry)
