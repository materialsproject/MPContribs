from importlib import import_module
from flask import jsonify
from flask.views import MethodViewType
from flasgger import SwaggerView as OriginalSwaggerView
from marshmallow_mongoengine import ModelSchema

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
            #cls.decorators = [login_required]
            cls.definitions = {schema_name: cls.Schema}
            cls.tags = [views_path[-2]]

class SwaggerView(OriginalSwaggerView, metaclass=SwaggerViewType):
    """A class-based view defining a `marshal` method to run query results
    through the accordung marshmallow schema"""
    def marshal(self, entries):
        # TODO check length of entries for many=True
        return jsonify(self.Schema().dump(entries, many=True).data)
