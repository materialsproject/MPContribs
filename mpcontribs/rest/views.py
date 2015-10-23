"""This module provides the views for the rest interface."""

import json
from django.core.exceptions import PermissionDenied
from django.shortcuts import render_to_response
from django.template import RequestContext
from mapi_basic.models import RegisteredUser
from bson.objectid import ObjectId
from mapi_basic import mapi_func
from test_site.settings import APPS

connector_path = 'mpcontribs.connector.Connector'

def index(request):
    from django.core.urlresolvers import reverse
    from .urls import urlpatterns
    urls = [ reverse(url.name) for url in urlpatterns[1:] ]
    ctx = RequestContext(request)
    ctx.update({'apps': APPS})
    return render_to_response("mpcontribs_rest_index.html", locals(), ctx)

@mapi_func(connector_path, supported_methods=["GET"], requires_api_key=True)
def check_contributor(request, mdb=None):
    """check whether user is in contrib(utor) group and return info."""
    is_contrib = request.user.groups.filter(name='contrib').exists()
    contributor = '{} {}'.format(request.user.first_name, request.user.last_name)
    return {"valid_response": True, 'response': {
        'is_contrib': is_contrib, 'contributor': contributor,
        'institution': request.user.institution
    }}

@mapi_func(connector_path, supported_methods=["POST", "GET"], requires_api_key=True)
def submit_contribution(request, mdb=None):
    """Submits a MPFile with a single contribution."""
    if not request.user.groups.filter(name='contrib').exists():
        raise PermissionDenied("MPFile submission open only to contributors.")
    project = request.user.institution # institution is required field in User
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        from importlib import import_module
        mod = import_module('mpcontribs.io.{}.mpfile'.format(request.POST['fmt']))
        MPFile = getattr(mod, 'MPFile')
        mpfile = MPFile.from_string(request.POST['mpfile'])
        if len(mpfile.document) > 1:
            raise ValueError('Invalid MPFile: Only single contributions allowed')
        cid = mdb.contrib_ad.submit_contribution(mpfile, contributor, project=project)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': str(cid)}

@mapi_func(connector_path, supported_methods=["POST", "GET"], requires_api_key=True)
def build_contribution(request, mdb=None):
    """Builds a single contribution into according material/composition"""
    if not request.user.groups.filter(name='contrib').exists():
        raise PermissionDenied("MPFile submission open only to contributors.")
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        cid = ObjectId(request.POST['cid'])
        url = mdb.contrib_build_ad.build(contributor, cid)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': url}

@mapi_func(connector_path, supported_methods=["POST", "GET"], requires_api_key=True)
def query_contributions(request, mdb=None):
    """Query the contributions collection"""
    criteria = json.loads(request.POST.get('criteria', '{}'))
    collection = request.POST.get('collection', 'contributions')
    projection = request.POST.get('projection', None)
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email
    )
    if json.loads(request.POST.get('contributor_only', 'true')):
        criteria['collaborators'] = {'$in': [contributor]}
    results = mdb.contrib_ad.query_contributions(
        criteria, projection=projection, collection=collection
    )
    return {"valid_response": True, "response": list(results)}

@mapi_func(connector_path, supported_methods=["POST", "GET"], requires_api_key=True)
def delete_contributions(request, mdb=None):
    """Delete a list of contributions"""
    if not request.user.is_staff:
        raise PermissionDenied("contributions deletion open only to staff right now.")
    from mpcontribs.utils import get_short_object_id
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

@mapi_func(connector_path, supported_methods=["POST", "GET"], requires_api_key=True)
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
