"""This module provides the views for the rest interface."""

# System imports
import datetime, json,logging
# Django imports
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest,\
    HttpResponseForbidden
# MP imports
from utils import connector, get_api_key, get_sandbox
from utils.connector import DBSandbox
from materials_django.settings import PYMATGEN_VERSION, DB_VERSION
from utils.encoders import MongoJSONEncoder

logger = logging.getLogger('mg.' + __name__)

def mapi_func(supported_methods=("GET", ), requires_api_key=False):

    """
    Decorator to standardize api checks and handle responses.

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
                # Get sandbox
                view_name = func.__name__
                sandbox = get_sandbox(request)
                try:
                    kwargs['mdb'] = DBSandbox(request.user, name=view_name,
                                              sandbox=sandbox)
                except connector.SandboxAuthzError as err:
                    raise PermissionDenied(str(err))
                logger.debug("@views.mapi_func db-sandbox={} view={}"
                             .format(kwargs['mdb'], view_name))
                # Call underlying function
                d = func(*args, **kwargs)
            except PermissionDenied as ex:
                d = {"valid_response": False, "error": str(ex)}
                return HttpResponseForbidden(
                    json.dumps(d), mimetype="application/json")
            except Exception as ex:
                d = {"valid_response": False, "error": str(ex)}
                return HttpResponseBadRequest(
                    json.dumps(d), mimetype="application/json")
            d["created_at"] = datetime.datetime.now().isoformat()
            d["version"] = {"db": DB_VERSION, "pymatgen": PYMATGEN_VERSION,
                            "rest": "1.0"}
            d["copyright"] = __copyright__
            #logging
            if check_api:
                points = len(d.get("response", []))
                log_ok = log_response(
                    request,
                    {"func": func.__name__, "args": args[1:],
                     "response": json.dumps(d, cls=MongoJSONEncoder)},
                    d, points, mdb=kwargs['mdb'])
                if not log_ok:
                    d = {"valid_response": False, "error": d["error"]}
                    return HttpResponseBadRequest(
                        json.dumps(d, cls=MongoJSONEncoder),
                        mimetype="application/json")
            return HttpResponse(json.dumps(d, cls=MongoJSONEncoder),
                                mimetype="application/json")
        return wrapped
    return wrap
