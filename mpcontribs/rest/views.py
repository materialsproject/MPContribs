# -*- coding: utf-8 -*-
"""This module provides the views for the rest interface."""

from __future__ import unicode_literals
import os, string
from subprocess import call
from bson.json_util import loads
from django.core.exceptions import PermissionDenied
from django.shortcuts import render_to_response
from django.contrib.auth.models import Group
from webtzite.connector import ConnectorBase
from bson.objectid import ObjectId
from webtzite import mapi_func, in_docker
from django.shortcuts import redirect
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

def get_endpoint(request):
    from django.core.urlresolvers import reverse
    url = reverse('mpcontribs_rest_index')[:-1]
    if os.environ.get('JPY_USER') is None and in_docker():
        return 'http://app:5000' + url
    return request.build_absolute_uri(url)

def index(request):
    jpy_user = os.environ.get('JPY_USER')
    if jpy_user:
        module_dir = os.path.dirname(__file__)
        cwd = os.getcwd()
        os.chdir(module_dir)
        with open('apidoc_template.json', 'r') as f:
             template = CustomTemplate(f.read())
             text = template.substitute({'URL': get_endpoint(request)})
             with open('apidoc.json', 'w') as f2:
                 f2.write(text)
        call(['apidoc', '-f "views.py"', '-f "_apidoc.py"', '--output', 'static'])
        os.chdir(cwd)
        return redirect(PROXY_URL_PREFIX + '/static_rest/index.html')
    return redirect('/static/index.html')

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
def build_contribution(request, db_type=None, mdb=None):
    """Builds a single contribution into according material/composition"""
    try:
        cid = ObjectId(request.POST['cid'])
        flag = request.POST.get('flag')
        if flag is None:
            response = mdb.contrib_build_ad.build(
                cid, api_key=request.user.api_key, endpoint=get_endpoint(request)
            )
        else:
            try:
                flag = bool(int(flag))
            except ValueError:
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
def cif(request, cid, structure_name, db_type=None, mdb=None):
    from mpcontribs.config import symprec
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
    required_keys = ['title', 'description', 'authors', 'urls']
    for mod_path in get_users_modules():
        if os.path.exists(os.path.join(mod_path, 'rest', 'rester.py')):
            UserRester = get_user_rester(mod_path)
            r = UserRester(request.user.api_key, endpoint=get_endpoint(request))
            if r.released and r.query is not None:
                criteria = {'mp_cat_id': identifier}
                criteria.update(dict(
                    ('content.{}'.format(k), {'$exists': 1})
                    for k in required_keys
                ))
                docs = r.query_contributions(
                    criteria=criteria,
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

@mapi_func(supported_methods=["GET", "POST"], requires_api_key=True)
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
    from mpcontribs.io.core.components import HierarchicalData, GraphicalData#, render_plot
    #from mpcontribs.io.core.utils import nested_dict_iter
    from mpcontribs.io.core.recdict import RecursiveDict, render_dict
    from django.core.urlresolvers import reverse
    from mpcontribs.config import mp_id_pattern

    embed = loads(request.POST.get('embed', 'true'))
    if embed:
        from selenium import webdriver
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
        from bs4 import BeautifulSoup
        options = webdriver.ChromeOptions()
        options.add_argument("no-sandbox")
        options.add_argument('--disable-dev-shm-usage')
        options.set_headless()
        host = 'browser' if in_docker() else '127.0.0.1'
        browser = webdriver.Remote(
            command_executor="http://{}:4444/wd/hub".format(host),
            desired_capabilities=DesiredCapabilities.CHROME,
            options=options
        )

    contrib = mdb.contrib_ad.query_contributions(
        {'_id': ObjectId(cid)},
        projection={'_id': 0, 'mp_cat_id': 1, 'content': 1, 'collaborators': 1}
    )[0]
    mpid = contrib['mp_cat_id']
    hdata = HierarchicalData(contrib['content'])
    #plots = GraphicalData(contrib['content'])
    title = hdata.get('title', 'No title available.')
    descriptions = hdata.get('description', 'No description available.').strip().split('.', 1)
    description = '{}.'.format(descriptions[0])
    if len(descriptions) > 1 and descriptions[1]:
        description += ''' <a onclick="read_more_{}()" id="read_more_{}">More &raquo;</a><span id="more_text_{}"
        hidden>{}</span>'''.format(cid, cid, cid, descriptions[1])
    authors = hdata.get('authors', 'No authors available.').split(',', 1)

    provenance = '<h5 style="margin: 5px;">{}'.format(authors[0])
    if len(authors) > 1:
        authors = authors[1].strip().replace(', ', '<br/>')
        provenance += ' <a class="mytooltip" href="#">et al.<span class="classic">' + authors + '</span></a>'
    provenance += '</h5>'
    urls = hdata.get('urls', {}).values()
    provenance += ''.join(['''<a href={}
        class="btn btn-link" role=button style="padding: 0"
        target="_blank"><i class="fa fa-book fa-border fa-lg"></i></a>'''.format(x)
        for x in urls if x
    ])

    #if plots:
    #    card = []
    #    for name, plot in plots.items():
    #        filename = '{}_{}.png'.format(mpid, name)
    #        cwd = os.path.dirname(__file__)
    #        filepath = os.path.abspath(os.path.join(
    #            cwd, '..', '..', 'webtzite', 'static', 'img', filename
    #        ))
    #        if not os.path.exists(filepath):
    #            render_plot(plot, filename=filepath)
    #        index = request.build_absolute_uri(reverse('webtzite_index')[:-1])
    #        imgdir = '/'.join([index.rsplit('/', 1)[0], 'static', 'img'])
    #        fileurl = '/'.join([imgdir, filename])
    #        card.append(fileurl)
    #else:
    data = RecursiveDict()
    for idx, (k,v) in enumerate(hdata.get('data', {}).items()):
        data[k] = v
        if idx >= 6:
            break # humans can grasp 7 items quickly

    if embed:
        data = render_dict(data, require=False, script_only=True)
        browser.execute_script(data)
        src = browser.page_source.encode("utf-8")
        bs = BeautifulSoup(src, 'html.parser')
        data = unicode(bs.body.style) + unicode(bs.body.table)
        browser.close()
    else:
        data = render_dict(data, webapp=True)

    is_mp_id = mp_id_pattern.match(mpid)
    collection = 'materials' if is_mp_id else 'compositions'
    more = reverse('mpcontribs_explorer_contribution', args=[collection, cid])
    more = request.build_absolute_uri(more)
    project = hdata.get('project')
    if project is not None:
        landing_page = reverse('mpcontribs_users_{}_explorer_index'.format(project))
        landing_page = request.build_absolute_uri(landing_page)

    card = '''
    <style>
    .mytooltip {{
          border-bottom: 1px dotted #000000;
          color: #000000; outline: none;
          cursor: help; text-decoration: none;
          position: relative;
    }}
    .mytooltip span {{
          margin-left: -999em;
          position: absolute;
    }}
    .mytooltip:hover span {{
      font-family: Calibri, Tahoma, Geneva, sans-serif;
      position: absolute;
      left: 1em;
      top: 2em;
      z-index: 99;
      margin-left: 0;
      width: 100px;
    }}
    .mytooltip:hover img {{
      border: 0;
      margin: -10px 0 0 -55px;
      float: left;
      position: absolute;
    }}
    .mytooltip:hover em {{
      font-family: Candara, Tahoma, Geneva, sans-serif;
      font-size: 1.2em;
      font-weight: bold;
      display: block;
      padding: 0.2em 0 0.6em 0;
    }}
    .classic {{ padding: 0.8em 1em; }}
    .custom {{ padding: 0.5em 0.8em 0.8em 2em; }}
    * html a:hover {{ background: transparent; }}
    .classic {{ background: #000000; color: #FFFFFF; }}
    #user_contribs .panel {{
        width: 97%;
        margin-bottom: 20px;
        background-color: #fff;
        border: 1px solid transparent;
        border-radius: 4px;
        -webkit-box-shadow: 0 1px 1px rgba(0,0,0,.05);
        box-shadow: 0 1px 1px rgba(0,0,0,.05);
    }}
    #user_contribs .panel-default {{
        border-color: #ddd;
    }}
    #user_contribs .panel-default>.panel-heading {{
        color: #333;
        background-color: #f5f5f5;
        border-color: #ddd;
    }}
    #user_contribs .panel-heading {{
        padding: 10px 15px;
        border-bottom: 1px solid transparent;
        border-top-left-radius: 3px;
        border-top-right-radius: 3px;
    }}
    #user_contribs .panel-body {{
        padding: 15px;
    }}
    </style>
    <div id="user_contribs">
    <div class="panel panel-default">
        <div class="panel-heading">
            <h4 class="panel-title">
                <a href="{}" target="_blank">{}</a>
                <a class="btn-sm btn-default pull-right" role="button"
                   style=" margin-top:-6px;"
                   href="{}" target="_blank">More Info</a>
            </h4>
        </div>
        <div class="panel-body" style="padding-left: 0px">
            <div class="col-md-12" style="padding-top: 0px">
                <div class="well pull-right"
                style="padding: 5px 5px 5px 5px; margin-bottom: 2px;
                margin-left: 5px;">{}</div>
                <blockquote class="blockquote"
                style="font-size: 13px; padding: 0px 10px;">{}</blockquote>
            </div>
            <div class="col-md-12" style="padding-right: 0px;">{}</div>
        </div>
    </div>
    <script>
        function read_more_{}() {{
            document.getElementById("more_text_{}").style.display = 'block';
            document.getElementById("read_more_{}").style.display = 'none';
        }};
    </script>
    </div>
    '''.format(
            landing_page, title, more, provenance, description, data, cid, cid, cid
    ).replace('\n', '')

    return {"valid_response": True, "response": card}

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
