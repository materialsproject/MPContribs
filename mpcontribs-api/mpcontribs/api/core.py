"""Custom meta-class and MethodView for Swagger"""

import os
import logging
from importlib import import_module
from flask.views import MethodViewType
from flasgger import SwaggerView as OriginalSwaggerView
from marshmallow_mongoengine import ModelSchema
from flask_mongorest.views import ResourceView

logger = logging.getLogger('app')


# https://github.com/pallets/flask/blob/master/flask/views.py
class SwaggerViewType(MethodViewType):
    """Metaclass for `SwaggerView` defining custom attributes"""

    def __init__(cls, name, bases, d):
        """initialize Schema, decorators, definitions, and tags"""
        super(SwaggerViewType, cls).__init__(name, bases, d)

        if not __name__ == cls.__module__:
            # e.g.: cls.__module__ = mpcontribs.api.projects.views
            views_path = cls.__module__.split('.')
            doc_path = '.'.join(views_path[:-1] + ['document'])
            doc_filepath = doc_path.replace('.', os.sep) + '.py'
            if os.path.exists(doc_filepath):
                cls.doc_name = views_path[-2].capitalize()
                Model = getattr(import_module(doc_path), cls.doc_name)
                cls.schema_name = cls.doc_name + 'Schema'
                cls.Schema = type(cls.schema_name, (ModelSchema, object), {
                    'Meta': type('Meta', (object,), dict(
                        model=Model, ordered=True, model_build_obj=False
                    ))
                })
                cls.definitions = {cls.schema_name: cls.Schema}
            cls.tags = [views_path[-2]]


class SwaggerView(OriginalSwaggerView, ResourceView, metaclass=SwaggerViewType):
    """A class-based view defining additional methods"""
