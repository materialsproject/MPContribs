# -*- coding: utf-8 -*-
"""This module provides the views for the rest interface."""

from __future__ import unicode_literals
import os
from bson.json_util import loads
from bson.objectid import ObjectId
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import Group
from webtzite.connector import ConnectorBase
from webtzite import mapi_func, in_docker

class Connector(ConnectorBase):
    def connect(self, **kwargs):
        super(Connector, self).connect(**kwargs)
        self.contribs_db = self.default_db
        db_type = kwargs.get('db_type')
        if db_type is not None:
            self.contribs_db = self.get_database(db_type)
        from mpcontribs.rest.adapter import ContributionMongoAdapter
        self.contrib_ad = ContributionMongoAdapter(self.contribs_db)
        from mpcontribs.builder import MPContributionsBuilder
        self.contrib_build_ad = MPContributionsBuilder(self.contribs_db)

ConnectorBase.register(Connector)

def get_endpoint(request):
    try:
        from django.core.urlresolvers import reverse
    except ImportError:
        from django.urls import reverse
    url = reverse('mpcontribs_rest_index')[:-1]
    return request.build_absolute_uri(url)

@mapi_func(supported_methods=["GET"], requires_api_key=True)
def check_contributor(request, db_type=None, mdb=None):
    """
    @api {get} /check_contributor?API_KEY=:api_key Trusted contributor?
    @apiVersion 0.0.0
    @apiName GetCheckContributor
    @apiGroup User

    @apiDescription Checked whether user with given API key is registered with
    the Materials Project as a trusted contributor.

    @apiParam {String} api_key User's unique API_KEY

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {Object} response Response dictionary
    @apiSuccess {Boolean} response.is_contrib User is trusted contributor
    @apiSuccess {String} response.contributor User's first and last name
    @apiSuccess {String} response.institution User's institution/project

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2016-05-19T16:36:17.011824",
            "valid_response": true,
            "response": {
                "contributor": "Patrick Huck",
                "is_contrib": true,
                "institution": "LBNL"
            }
        }
    """
    group_added, contributor_added = False, False
    if not Group.objects.filter(name='contrib').exists():
        g = Group(name='contrib')
        g.save()
        group_added = True
    if request.user.is_superuser:
        g = Group.objects.get(name='contrib')
        if not g.user_set.exists():
            g.user_set.add(request.user)
            g.save()
            request.user.save()
            contributor_added = True
    is_contrib = request.user.groups.filter(name='contrib').exists()
    contributor = '{} {}'.format(request.user.first_name, request.user.last_name)
    return {"valid_response": True, 'response': {
        'is_contrib': is_contrib, 'contributor': contributor,
        'institution': request.user.institution,
        'group_added': group_added, 'contributor_added': contributor_added
    }}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def submit_contribution(request, db_type=None, mdb=None):
    """
    @api {post} /submit?API_KEY=:api_key Submit contribution
    @apiVersion 0.0.0
    @apiName PostSubmitContribution
    @apiGroup Contribution
    @apiPermission contrib
    @apiIgnore

    @apiDescription Submit a MPFile containing a single contribution

    @apiParam {String} api_key User's unique API_KEY

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {String} response Assigned contribution identifier

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2016-05-19T16:36:17.011824",
            "valid_response": true,
            "response": "5733904537202d12f59e896d"
        }
    """
    if not request.user.groups.filter(name='contrib').exists():
        raise PermissionDenied("MPFile submission open only to contributors.")
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        from importlib import import_module
        mod = import_module('mpcontribs.io.{}.mpfile'.format(request.POST['fmt']))
        MPFile = getattr(mod, 'MPFile')
        mpfile = MPFile.from_string(request.POST['mpfile'])
        if len(mpfile.document) > 1:
            raise ValueError('Invalid MPFile: Only single contributions allowed')
        # institution is required field in User
        project = mpfile.document[mpfile.ids[0]].get('project', request.user.institution)
        cid = mdb.contrib_ad.submit_contribution(mpfile, contributor, project=project)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': str(cid)}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def query_contributions(request, db_type=None, mdb=None):
    """
    @api {post} /query?API_KEY=:api_key Query contributions
    @apiVersion 0.0.1
    @apiName PostQueryContributions
    @apiGroup Contribution

    @apiDescription Query the contributions, materials, or compositions
    collections given specific criteria and projection

    @apiParam {String} api_key User's unique API_KEY
    @apiParam {String} collection Collection to run query against
    ('contributions', 'materials', or 'compositions')
    @apiParam {json} criteria Query criteria (filter documents)
    @apiParam {json} projection Query projection (reduce returned doc output)

    @apiParamExample {json} Request-Example:
        {
            "collection": "contributions",
            "criteria": { "_id": "mp-2715" },
            "projection": { "content.data": 1 }
        }

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {Object[]} response List of shortened contribution docs (defined
    as follows) if collection == 'contributions' else list of materials or
    compositions docs (limited to one doc)
    @apiSuccess {String} response._id Contribution identifier
    @apiSuccess {String[]} response.collaborators List of collaborators
    @apiSuccess {String} response.identifier MP category identifier (mp-id or
    composition)

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2016-05-20T16:15:26.909038",
            "valid_response": true,
            "response": [
                {
                    "_id": "5a862202d4f1443a18fab254",
                    "content": {
                        "data": {
                            "ΔE-KS": {
                                "indirect": "0.0991 eV",
                                "direct": "0.275 eV"
                            },
                            "ΔE-QP": {
                                "indirect": "0.135 eV",
                                "direct": "0.311 eV"
                            },
                            "C": "0.0357 eV"
                        }
                    },
                    "collaborators": [ "Patrick Huck" ]
                }, ...
            ]
        }
    """
    criteria = loads(request.POST.get('criteria', '{}'))
    limit = loads(request.POST.get('limit', '0'))
    collection = request.POST.get('collection', 'contributions')
    if not collection: collection = 'contributions' # empty string check
    projection = loads(request.POST.get('projection', 'null'))
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email
    )
    if loads(request.POST.get('contributor_only', 'false')):
        criteria['collaborators'] = {'$in': [contributor]}
    results = list(mdb.contrib_ad.query_contributions(
        criteria, projection=projection, collection=collection, limit=limit
    ))
    # TODO collaborators is a dict now! {'name': .., 'email': ...}
    #if collection == 'contributions':
    #    # remove email addresses from output
    #    for doc in results:
    #        doc['collaborators'] = [
    #            ' '.join(collaborator.split()[:2])
    #            for collaborator in doc['collaborators']
    #        ]
    return {"valid_response": True, "response": results}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def count(request, db_type=None, mdb=None):
    criteria = loads(request.POST.get('criteria', '{}'))
    collection = request.POST.get('collection', 'contributions')
    if not collection:
        collection = 'contributions' # empty string check
    cnt = mdb.contrib_ad.count(criteria, collection=collection)
    return {"valid_response": True, "response": cnt}

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def delete_contributions(request, db_type=None, mdb=None):
    """Delete a list of contributions"""
    #if not request.user.is_staff:
    #    raise PermissionDenied("contributions deletion open only to staff right now.")
    from mpcontribs.utils import get_short_object_id
    cids = [ ObjectId(cid) for cid in loads(request.POST['cids'])]
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
def update_collaborators(request, db_type=None, mdb=None):
    """Update the list of collaborators"""
    from webtzite.models import RegisteredUser
    if not request.user.is_staff:
        raise PermissionDenied("collaborators update open only to staff right now.")
    collaborators = loads(request.POST['collaborators'])
    cids = loads(request.POST['cids'])
    #mode = request.POST['mode']
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

@mapi_func(supported_methods=["GET"], requires_api_key=True)
def datasets(request, identifier, db_type=None, mdb=None):
    """
    @api {get} /datasets/:identifier?API_KEY=:api_key List of Datasets
    @apiVersion 0.2.0
    @apiName GetDatasets
    @apiGroup Contribution

    @apiDescription Returns a list of datasets and their respective
    contributions for a given identifier (mp-id or composition)

    @apiParam {String} api_key User's unique API_KEY

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {Object} response Response List of Dictionaries
    @apiSuccess {Boolean} response.title Dataset title
    @apiSuccess {Boolean} response.authors Dataset authors
    @apiSuccess {Boolean} response.description Dataset description
    @apiSuccess {Boolean} response.urls Dataset urls
    @apiSuccess {String} response.cids List of contribution id's

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2017-08-09T19:59:59.936618",
            "valid_response": true,
            "response": [
                {
                    "_id": "carrier_transport",
                    "description": "...",
                    "title": "Carrier Transport",
                    "urls": {
                        "url": "https://www.nature.com/articles/sdata201785",
                        "doi": "https://doi.org/10.1038/sdata.2017.85"
                    },
                    "authors": "F. Ricci, W. Chen, ...",
                    "cids": [ "5ac0a17fd4f1443de2674074" ]
                }, ...
            ]
        }
    """
    contributions = []
    required_keys = ['title', 'description', 'authors', 'urls']
    projection = {'identifier': 1, 'project': 1, '_id': 1}
    projection.update(dict(('content.'+k, 1) for k in required_keys))
    group = {'_id': '$project', 'cids': {'$push': '$_id'}}
    group.update(dict((k, {'$first': '$content.'+k}) for k in required_keys))
    docs = list(mdb.contribs_db.contributions.aggregate([
        {'$match': {'identifier': identifier}}, {'$project': projection}, {'$group': group}
    ]))
    return {"valid_response": True, "response": docs}

@mapi_func(supported_methods=["GET"], requires_api_key=True)
def groupadd(request, token, db_type=None, mdb=None):
    coll = mdb.contribs_db.groupadd_tokens
    doc = coll.find_one({'token': token})
    if doc is None:
        return {"valid_response": False, "error": "invalid token: {}".format(token)}
    group_exists = Group.objects.filter(name=doc['group']).exists()
    if request.user.is_superuser and not group_exists:
        g = Group(name=doc['group'])
        g.save()
    group = Group.objects.get(name=doc['group'])
    group.user_set.add(request.user)
    return {"valid_response": True, 'response': 'user access granted.'}

@mapi_func(supported_methods=["GET"], requires_api_key=True)
def landing_pages(request, db_type=None, mdb=None):
    coll = mdb.contribs_db.contributions
    results = [coll.find_one(
        {'project': project},
        {'project': 1, 'content.title': 1, 'content.authors': 1}
    ) for project in coll.distinct("project")]
    return {"valid_response": True, 'response': results}
