import re
from requests import get
from importlib import import_module
from flask import request, current_app
from flask.views import MethodViewType
from flasgger import SwaggerView as OriginalSwaggerView
from marshmallow_mongoengine import ModelSchema
from flask_mongoengine import BaseQuerySet
from functools import wraps
from flask_json import as_json, JsonError

HEADER = 'X-API-KEY'

def catch_error(f):
    @wraps(f)
    def reraise(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as ex:
            raise JsonError(error=str(ex))
    return reraise

def login_required(f):
    @wraps(f)
    def authenticate(*args, **kwargs):
        # TODO SSL check?
        if HEADER not in request.headers:
            raise JsonError(401, error='{} header missing'.format(HEADER))
        api_key = request.headers[HEADER]
        if not re.match('^[0-9,A-Z,a-z]{16}$', api_key):
            raise JsonError(401, error='{} format invalid'.format(HEADER))
        api_check_endpoint = current_app.config.get('API_CHECK_ENDPOINT')
        if not api_check_endpoint:
            raise JsonError(500, error='API_CHECK_ENDPOINT not set!')
        headers = {HEADER: api_key}
        api_check_response = get(api_check_endpoint, headers=headers).json()
        if not api_check_response['api_key_valid']:
            raise JsonError(401, error='{} invalid'.format(HEADER))
        if request.method == 'POST' and not api_check_response['is_staff']:
            raise JsonError(401, error='staff status required for POST')
        return f(*args, **kwargs)
    return authenticate

# https://github.com/pallets/flask/blob/master/flask/views.py
class SwaggerViewType(MethodViewType):
    """Metaclass for `SwaggerView` ..."""
    def __init__(cls, name, bases, d):
        super(SwaggerViewType, cls).__init__(name, bases, d)
        if not __name__ == cls.__module__:
            # e.g.: cls.__module__ = mpcontribs.api.provenances.views
            views_path = cls.__module__.split('.')
            doc_path = '.'.join(views_path[:-1] + ['document'])
            doc_name = views_path[-2].capitalize()
            Model = getattr(import_module(doc_path), doc_name)
            schema_name = doc_name + 'Schema'
            cls.Schema = type(schema_name, (ModelSchema, object), {
                'Meta': type('Meta', (object,), dict(model=Model, ordered=True))
            })
            cls.decorators = [as_json, catch_error, login_required]
            cls.definitions = {schema_name: cls.Schema}
            cls.tags = [views_path[-2]]

class SwaggerView(OriginalSwaggerView, metaclass=SwaggerViewType):
    """A class-based view defining a `marshal` method to run query results
    through the accordung marshmallow schema"""
    def marshal(self, entries):
        many = isinstance(entries, BaseQuerySet)
        return self.Schema().dump(entries, many=many).data
