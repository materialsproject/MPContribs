"""This module provides the views for the rest interface."""

import os, string
from subprocess import call
from bson.json_util import loads
from django.core.exceptions import PermissionDenied
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.contrib.auth.models import Group
from webtzite.connector import ConnectorBase
from bson.objectid import ObjectId
from webtzite import mapi_func
from django.shortcuts import redirect
from importlib import import_module
from test_site.settings import PROXY_URL_PREFIX

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

class CustomTemplate(string.Template):
    delimiter = '$$'

def get_endpoint():
    from django.core.urlresolvers import reverse
    return reverse('mpcontribs_rest_index')[:-1]

def index(request):
    endpoint = request.build_absolute_uri(get_endpoint())
    module_dir = os.path.dirname(__file__)
    cwd = os.getcwd()
    os.chdir(module_dir)
    with open('apidoc_template.json', 'r') as f:
         template = CustomTemplate(f.read())
         text = template.substitute({'URL': endpoint})
         with open('apidoc.json', 'w') as f2:
             f2.write(text)
    call(['apidoc', '-f "views.py"', '-f "_apidoc.py"', '--output', 'static'])
    os.chdir(cwd)
    return redirect(PROXY_URL_PREFIX + '/static_rest/index.html')

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

@mapi_func(supported_methods=["POST", "GET"], requires_api_key=True)
def build_contribution(request, db_type=None, mdb=None):
    """Builds a single contribution into according material/composition"""
    # TODO collaborator check (build doc needs 'collaborators' entry)
    if not request.user.groups.filter(name='contrib').exists():
        raise PermissionDenied("MPFile submission open only to contributors.")
    contributor = '{} {} <{}>'.format(
        request.user.first_name, request.user.last_name, request.user.email)
    try:
        cid = ObjectId(request.POST['cid'])
        flag = request.POST.get('flag')
        if flag is None:
            endpoint = request.build_absolute_uri(get_endpoint())
            response = mdb.contrib_build_ad.build(
                contributor, cid, api_key=request.user.api_key, endpoint=endpoint
            )
        else:
            try:
                flag = bool(int(flag))
            except:
                if flag in ['True', 'False']:
                    flag = True if flag == 'True' else False
                else:
                    raise ValueError('flag {} is not in boolean'.format(flag))
            mdb.contrib_build_ad.set_build_flag(cid, flag)
            response = 'build flag for {} set to {}'.format(cid, flag)
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

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
            "collection": "materials",
            "criteria": { "_id": "mp-30" },
            "projection": {
                "_id": 0, "LBNL.5733704637202d12f448fc59.tree_data": 1
            }
        }

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {Object[]} response List of shortened contribution docs (defined
    as follows) if collection == 'contributions' else list of materials or
    compositions docs (limited to one doc)
    @apiSuccess {String} response._id Contribution identifier
    @apiSuccess {String[]} response.collaborators List of collaborators
    @apiSuccess {String} response.mp_cat_id MP category identifier (mp-id or
    composition)

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2016-05-20T16:15:26.909038",
            "valid_response": true,
            "response": [
                {
                    "_id": "57336b0137202d12f6d50b37",
                    "collaborators": ["Patrick Huck"],
                    "mp_cat_id": "mp-134"
                }, {
                    "_id": "5733704637202d12f448fc59",
                    "collaborators": ["Patrick Huck"],
                    "mp_cat_id": "mp-30"
                }
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
    if collection == 'contributions':
        # remove email addresses from output
        for doc in results:
            doc['collaborators'] = [
                ' '.join(collaborator.split()[:2])
                for collaborator in doc['collaborators']
            ]
    return {"valid_response": True, "response": results}

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

@mapi_func(supported_methods=["GET"], requires_api_key=True)
def cif(request, cid, structure_name, db_type=None, mdb=None):
    from mpcontribs.config import symprec, mp_level01_titles
    from mpcontribs.io.core.components import Structures
    from pymatgen.io.cif import CifWriter
    contrib = mdb.contrib_ad.query_contributions(
        {'_id': ObjectId(cid)},
        projection={'_id': 0, 'mp_cat_id': 1, 'content': 1, 'collaborators': 1}
    )[0]
    structure = Structures(contrib['content']).get(structure_name)
    if structure:
        cif = CifWriter(structure, symprec=symprec).__str__()
        return {"valid_response": True, "response": cif}
    return {"valid_response": False,
            "response": "{} not found!".format(structure_name)}

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
    @apiSuccess {String} response.provenance_keys Provenance keys for dataset
    @apiSuccess {String} response.cids List of contribution id's

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2017-08-09T19:59:59.936618",
            "valid_response": true,
            "response": [
                {
                    "cids": [ "598b69700425d5032cc8e586" ],
                    "provenance_keys": [ "source" ],
                    "title": "Optical constants of Cu-Zn (Copper-zinc alloy, Brass)"
                }
            ]
        }
    """
    from mpcontribs.users_modules import get_users_modules, get_user_rester
    contributions = []
    for mod_path in get_users_modules():
        if os.path.exists(os.path.join(mod_path, 'rest', 'rester.py')):
            mod_path_split = mod_path.split(os.sep)[-3:]
            m = import_module('.'.join(mod_path_split + ['rest', 'rester']))
            UserRester = getattr(m, get_user_rester(mod_path_split[-1]))
            endpoint = request.build_absolute_uri(get_endpoint())
            r = UserRester(request.user.api_key, endpoint=endpoint)
            if r.released and r.query is not None:
                docs = r.query_contributions(
                    criteria={'mp_cat_id': identifier, 'content.title': {'$exists': 1}},
                    projection={'content.title': 1, 'mp_cat_id': 1}
                )
                if docs:
                    contrib = {}
                    contrib['title'] = docs[0]['content']['title']
                    contrib['cids'] = []
                    for d in docs:
                        contrib['cids'].append(d['_id'])
                    contrib['provenance_keys'] = map(str, r.provenance_keys)
                    contributions.append(contrib)
    return {"valid_response": True, "response": contributions}

@mapi_func(supported_methods=["POST"], requires_api_key=True)
def get_card(request, cid, db_type=None, mdb=None):
    """
    @api {post} /card/:cid?API_KEY=:api_key Contribution Card/Preview
    @apiVersion 0.2.0
    @apiName PostGetCard
    @apiGroup Contribution

    @apiDescription Either returns a string containing html for hierarchical
    data, or if existent, a list of URLs for static versions of embedded graphs.

    @apiParam {String} api_key User's unique API_KEY
    @apiParam {json} provenance_keys List of provenance keys

    @apiSuccess {String} created_at Response timestamp
    @apiSuccess {Bool} valid_response Response is valid
    @apiSuccess {String} response Response preview of h- or t-data/graphs ("card")

    @apiSuccessExample Success-Response:
        HTTP/1.1 200 OK
        {
            "created_at": "2017-08-09T19:59:59.936618",
            "valid_response": true,
            "response": ["<graph-url>"]
        }
    """
    from mpcontribs.io.core.components import Tree, Plots, render_plot
    from mpcontribs.io.core.utils import nested_dict_iter
    from mpcontribs.io.core.recdict import RecursiveDict, render_dict
    from django.template import Template, Context
    from django.core.urlresolvers import reverse
    prov_keys = loads(request.POST.get('provenance_keys', '["title"]'))
    contrib = mdb.contrib_ad.query_contributions(
        {'_id': ObjectId(cid)},
        projection={'_id': 0, 'mp_cat_id': 1, 'content': 1, 'collaborators': 1}
    )[0]
    mpid = contrib['mp_cat_id']
    hdata = Tree(contrib['content'])
    plots = Plots(contrib['content'])
    if plots:
        card = []
        for name, plot in plots.items():
            filename = '{}_{}.png'.format(mpid, name)
            cwd = os.path.dirname(__file__)
            filepath = os.path.abspath(os.path.join(
                cwd, '..', '..', 'webtzite', 'static', 'img', filename
            ))
            if not os.path.exists(filepath):
                render_plot(plot, filename=filepath)
            index = request.build_absolute_uri(reverse('webtzite_index')[:-1])
            imgdir = '/'.join([index.rsplit('/', 1)[0], 'static', 'img'])
            fileurl = '/'.join([imgdir, filename])
            card.append(fileurl)
    else:
        info = hdata.get('highlights', hdata.get('explanation', hdata.get('description')))
        card = RecursiveDict({'info': info}) if info is not None else RecursiveDict()
        for k,v in hdata.items():
            if k not in prov_keys and k != 'abbreviations':
                card[k] = v
        #card = RecursiveDict()
        #for idx, (k,v) in enumerate(nested_dict_iter(sub_hdata)):
        #    card[k] = v
        #    if idx >= 6:
        #        break # humans can grasp 7 items quickly
    return {"valid_response": True, "response": card}
