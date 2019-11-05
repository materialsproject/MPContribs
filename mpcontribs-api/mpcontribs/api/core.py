from importlib import import_module
from flask.views import MethodViewType
from flasgger import SwaggerView as OriginalSwaggerView
from marshmallow_mongoengine import ModelSchema
from flask_mongoengine import BaseQuerySet
from functools import wraps
from flask_json import as_json, JsonError


def catch_error(f):
    @wraps(f)
    def reraise(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as ex:
            raise JsonError(error=str(ex))
    return reraise


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
            cls.decorators = [as_json, catch_error]
            cls.definitions = {schema_name: cls.Schema}
            cls.tags = [views_path[-2]]


class SwaggerView(OriginalSwaggerView, metaclass=SwaggerViewType):
    """A class-based view defining a `marshal` method to run query results
    through the according marshmallow schema"""
    def marshal(self, entries):
        many = isinstance(entries, BaseQuerySet) or isinstance(entries, list)
        return self.Schema().dump(entries, many=many).data
