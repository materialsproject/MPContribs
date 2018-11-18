import re, inspect, logging
from requests import get
from importlib import import_module
from marshmallow_mongoengine import fields
from flask import request, current_app
from flask_rebar import HandlerRegistry, errors, messages
from flask_rebar.authenticators.base import Authenticator
from flask_rebar.swagger_generation.swagger_generator import \
        SwaggerV2Generator, _convert_header_api_key_authenticator
from flask_rebar.swagger_generation.marshmallow_to_swagger import \
        response_converter_registry, StringConverter
from werkzeug.exceptions import MethodNotAllowed
from mpcontribs.api.config import DEBUG

ALLOWED_METHODS = ('GET', )
logger = logging.getLogger('registry')

class ObjectIdConverter(StringConverter):
    MARSHMALLOW_TYPE = fields.ObjectId

response_converter_registry.register_type(ObjectIdConverter())

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

def get_members(module, typ):
    return [
        m for m in inspect.getmembers(module, typ)
        if m[1].__module__ == module.__name__
    ]

def setup_registry(conn):
    authenticator = HeaderApiKeyAuthenticator('X-API-KEY', 'MAPI_KEY')
    api_pkg_path = __name__.split('.')[:-1]
    db_name = api_pkg_path[0]
    #collections = conn[db_name].list_collection_names() # TODO replace below
    collections = ['contributions', 'provenances']

    # TODO add https scheme
    # TODO default_response_schema ?
    swaggen = SwaggerV2Generator(
        title='MPContribs API', version=None,
        description='Operations to retrieve materials data contributed to MP'
    )
    swaggen.authenticator_converters = { # reset default
        HeaderApiKeyAuthenticator: _convert_header_api_key_authenticator
    }
    registry = HandlerRegistry(swagger_generator=swaggen)
    registry.set_default_authenticator(authenticator)

    for collection in collections:
        module_path = '.'.join(api_pkg_path + [collection])

        try:
            module = import_module(module_path)
        except ModuleNotFoundError:
            logger.warning('API module {} not found!'.format(module_path))
            continue

        functions = get_members(module, inspect.isfunction)
        classes = dict(get_members(module, inspect.isclass))

        for name, func in functions:
            try:
                method, rule = func.__name__.split('_')
            except ValueError:
                logger.warning('Invalid function name {}'.format(func.__name__))
                continue

            if method.upper() not in ALLOWED_METHODS:
                raise MethodNotAllowed(
                    valid_methods=ALLOWED_METHODS,
                    description='`{}` not a valid function prefix'.format(method)
                )

            kwargs = dict(rule='/'+rule, method=method.upper())
            if DEBUG:
                kwargs['authenticator'] = None
            document = rule.capitalize()
            schema_name = method.capitalize() + document + 'QuerySchema'
            QuerySchema = classes.get(schema_name)
            if QuerySchema is not None:
                kwargs['query_string_schema'] = QuerySchema()
            MarshalSchema = classes.get(document + 'Schema')
            if MarshalSchema is not None:
                kwargs['marshal_schema'] = MarshalSchema()
            registry.add_handler(func, **kwargs)
            logger.info('added `{}` handler at /{}'.format(method, rule))

    return registry
