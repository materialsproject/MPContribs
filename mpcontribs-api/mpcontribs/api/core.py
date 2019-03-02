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

def catch_error(f):
    @wraps(f)
    def reraise(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as ex:
            raise JsonError(error=str(ex))
    return reraise

#from email.utils import parseaddr
## a POST request to /rest/api_check can contain a permissions dict with
## keys: '*' or valid email address; values: 'read' or 'readWrite'
## `*`: according permission applies to any user (with an API key)
#permission = None
#if request.method == 'POST':
#    body = request.body.replace(b"\'", b"\"")
#    data = json.loads(body)
#
#    # remove and check wildcard permission (any MP user)
#    # can't be readWrite, only None or read
#    wildcard_permission = data.pop("*", None)
#    if wildcard_permission and wildcard_permission != "read":
#        raise PermissionDenied("wildcard permission can only be `read`"
#                               " but is {}".format(wildcard_permission))
#
#    # validate the POST data
#    cleaned_data = dict(
#        (k, v) for k, v in data.items()
#        if v in ['read', 'readWrite'] and '@' in parseaddr(k)[1]
#    )
#    if not cleaned_data:
#        msg = "Need at least one (staff) entry in permissions dict." \
#                if wildcard_permission else \
#                "validated permissions dict is empty."
#        raise PermissionDenied(msg)
#
#    # check whether/which email (key) matches request.user.email, and, if so,
#    # return the according permissions string (value) [None, 'read', 'readWrite']
#    # (returning permission obscures direct comparison of API key and email)
#    for email, permission in cleaned_data.items():
#        if email == request.user.email:
#            break # this email/permission belongs to API key
#    else: # permissions entry for request.user not found; use wildcard
#        email, permission = '*', wildcard_permission
#
#    # make sure that the permissions dict contains at least one staff
#    # email with readWrite (restricts creation/insertion of new
#    # documents into DB and ensures that staff can always edit)
#    print(cleaned_data)
#    if permission == 'readWrite':
#        if len(cleaned_data) == 1 and not request.user.is_staff:
#            msg = "Document creation only open to staff."
#            raise PermissionDenied(msg)
#        else:
#            # TODO there needs to be another staff email in permissions dict
#            pass

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
    through the accordung marshmallow schema"""
    def marshal(self, entries):
        many = isinstance(entries, BaseQuerySet)
        return self.Schema().dump(entries, many=many).data
