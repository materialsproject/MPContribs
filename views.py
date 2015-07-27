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
from mpcontribs.io.mpfile import MPFile
from bson.objectid import ObjectId
from mpcontribs.utils import get_short_object_id

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
                    {"func": func.__name__, "args": args[1:]},
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

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def submit_contribution(request, mdb=None):
    """Submits a MPFile with a single contribution."""
    if not request.user.is_staff:
        raise PermissionDenied("MPFile submission open only to staff right now.")
    project = request.user.institution # institution is required field in User
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        mpfile = MPFile.from_string(request.POST['mpfile'])
        if len(mpfile.document) > 1:
            raise ValueError('Invalid MPFile: Only single contributions allowed')
        cid = mdb.contrib_ad.submit_contribution(mpfile, contributor, project=project)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'cid': cid}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def build_contribution(request, mdb=None):
    """Builds a single contribution into according material/composition"""
    if not request.user.is_staff:
        raise PermissionDenied("MPFile submission open only to staff right now.")
    project = request.user.institution # institution is required field in User
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        cid = ObjectId(request.POST['cid'])
        url = mdb.contrib_build_ad.build(contributor, cid)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'url': url}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def query_contributions(request, mdb=None):
    """Query the contributions collection"""
    if not request.user.is_staff:
        raise PermissionDenied("contributions query open only to staff right now.")
    criteria = json.loads(request.POST.get('criteria', '{}'))
    collection = json.loads(request.POST.get('collection', 'contributions'))
    projection = json.loads(request.POST.get('projection', None))
    # contribution query only depends on contributor_email (not project)
    # query checks whether contributor_email is in collaborators list of contribution
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email
    )
    if json.loads(request.POST.get('contributor_only', 'true')):
        criteria['collaborators'] = {'$in': [contributor]}
    results = mdb.contrib_ad.query_contributions(
        criteria, projection=projection, collection=collection
    )
    return {"valid_response": True, "response": list(results)}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def delete_contributions(request, mdb=None):
    """Delete a list of contributions"""
    if not request.user.is_staff:
        raise PermissionDenied("contributions deletion open only to staff right now.")
    cids = [ ObjectId(cid) for cid in json.loads(request.POST['cids'])]
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email
    )
    project = request.user.institution # institution is required field in User
    for doc in mdb.contrib_ad.db.contributions.find(
        {'_id': {'$in': cids}}, {'collaborators': 1}
    ):
        if contributor not in doc['collaborators']:
            cid_short = get_short_object_id(doc['_id'])
            raise PermissionDenied(
                "Deletion stopped: deleting contribution #{} not"
                " allowed due to insufficient permissions of {}!"
                " Ask someone of {} to make you a collaborator on"
                " contribution #{}.".format(cid_short, contributor,
                                           doc['collaborators'], cid_short))
    criteria = {'collaborators': {'$in': [contributor]}, '_id': {'$in': cids}}
    mdb.contrib_build_ad.delete(project, cids)
    results = mdb.contrib_ad.delete_contributions(criteria)
    return {"valid_response": True, "response": results}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def update_collaborators(request, mdb=None):
    """Update the list of collaborators"""
    if not request.user.is_staff:
        raise PermissionDenied("collaborators update open only to staff right now.")
    collaborators = json.loads(request.POST['collaborators'])
    cids = json.loads(request.POST['cids'])
    mode = request.POST['mode']
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email
    )
    for doc in mdb.contrib_ad.db.contributions.find(
        {'_id': {'$in': cids}}, {'collaborators': 1}
    ):
        if contributor not in doc['collaborators']:
            cid = doc['contribution_id']
            raise PermissionDenied(
                "Collaborator Update stopped: updating collaborators for"
                " contribution {} not allowed due to insufficient permissions"
                " of {}! Ask someone of {} to make you a collaborator on"
                " contribution {}.".format(
                    cid, contributor, doc['collaborators'], cid
                ))
    # process collaborators shortcuts into author strings
    collaborator_emails = []
    for collaborator in collaborators:
        # TODO input check for collaborators
        # TODO test with different users
        first_name_initial, last_name = collaborator.split('.')
        user = RegisteredUser.objects.get(
            last_name__iexact=last_name,
            first_name__istartswith=first_name_initial
        )
        collaborator_emails.append('{} {} <{}>'.format(
            user.first_name, user.last_name, user.email
        ))
    # 2. update collaborators in contributions collection based on mode
    # 3. build update into materials collection
    #criteria = {
    #    'collaborators': {'$in': [contributor]},
    #    'contribution_id': {'$in': cids}
    #}
    #results = mdb.contrib_ad.delete_contributions(criteria)
    #mdb.contrib_build_ad.delete(cids)
    return {"valid_response": True, "response": collaborator_emails}
