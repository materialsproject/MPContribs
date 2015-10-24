import datetime, json, bson
from importlib import import_module
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.encoding import force_unicode
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest,\
    HttpResponseForbidden

class MongoJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, bson.objectid.ObjectId):
            return force_unicode(obj)
        return super(MongoJSONEncoder, self).default(obj)

def get_api_key(request):
    """Utility function to extract API KEY from an HTTP request object."""
    return (request.META.get('HTTP_X_API_KEY', None) or
            request.GET.get('API_KEY', None) or
            request.POST.get('API_KEY', None))

def mapi_func(supported_methods=("GET",), requires_api_key=False):
    """Decorator to standardize api checks and handle responses.

    Args:
        requires_api_key:
            Whether an API key is required.
    """
    def wrap(func):
        def wrapped(*args, **kwargs):
            request = args[0]
            check_api = (not request.is_ajax()) and requires_api_key
            try:
                if request.method not in supported_methods:
                    raise PermissionDenied("Invalid request method.")
                # Get API key, if required
                if check_api:
                    api_key = get_api_key(request)
                    if not api_key:
                        raise PermissionDenied("API_KEY is not supplied.")
                    if not hasattr(request.user, "api_key") \
                            or api_key != request.user.api_key:
                        raise PermissionDenied("API_KEY is not a valid key.")
                # set mdb
                try:
                    func_module = import_module(func.__module__)
                    Connector = getattr(func_module, 'Connector')
                    kwargs['mdb'] = Connector(request.user)
                except:
                    from mapi_basic.connector import ConnectorBase
                    kwargs['mdb'] = ConnectorBase(request.user)
                # Call underlying function
                d = func(*args, **kwargs)
            except PermissionDenied as ex:
                d = {"valid_response": False, "error": str(ex)}
                return HttpResponseForbidden(
                    json.dumps(d), content_type="application/json")
            except Exception as ex:
                d = {"valid_response": False, "error": str(ex)}
                return HttpResponseBadRequest(
                    json.dumps(d), content_type="application/json")
            d["created_at"] = datetime.datetime.now().isoformat()
            return HttpResponse(json.dumps(d, cls=MongoJSONEncoder),
                                content_type="application/json")
        return wrapped
    return wrap
