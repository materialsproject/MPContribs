from __future__ import division, unicode_literals
import six, bson, os
from importlib import import_module
from bson.json_util import dumps, loads
from webtzite.rester import MPResterBase, MPResterError

class MPContribsRester(MPResterBase):
    """convenience functions to interact with MPContribs REST interface"""
    def __init__(self, api_key=None, endpoint=None, dbtype='mpcontribs_read', test_site=False):
        if api_key is None:
            api_key = os.environ.get('PMG_MAPI_KEY')
        if endpoint is None:
            endpoint = os.environ.get(
                'PMG_MAPI_ENDPOINT', 'http://alpha.materialsproject.org/mpcontribs/rest'
            )
        if test_site:
            # override api_key and endpoint with test_site values
            jpy_user = os.environ.get('JPY_USER')
            if not jpy_user:
                raise ValueError('Cannot connect to test_site outside MP JupyterHub!')
            flaskproxy = 'https://jupyterhub.materialsproject.org/flaskproxy'
            endpoint = '/'.join([flaskproxy, jpy_user, 'test_site/mpcontribs/rest'])
            from webtzite.models import RegisteredUser
            email = jpy_user + '@users.noreply.github.com'
            try:
                u = RegisteredUser.objects.get(email=email)
            except RegisteredUser.DoesNotExist:
                login_url = '/'.join([flaskproxy, jpy_user, 'test_site/login'])
                raise ValueError('Go to {} and register first!'.format(login_url))
            api_key = u.api_key
        super(MPContribsRester, self).__init__(
          api_key=api_key, endpoint=endpoint
        )
        self.dbtype = dbtype

    @property
    def query(self):
        return None

    @property
    def provenance_keys(self):
        raise NotImplementedError('Implement `provenance_keys` property in Rester!')

    @property
    def released(self):
        return False

    def _make_request(self, sub_url, payload=None, method="GET"):
        return super(MPContribsRester, self)._make_request(
          '/'.join([sub_url, self.dbtype]), payload=payload, method=method
        )

    def get_cid_url(self, doc):
        """infer URL for contribution detail page from MongoDB doc"""
        from mpcontribs.config import mp_id_pattern
        is_mp_id = mp_id_pattern.match(doc['mp_cat_id'])
        collection = 'materials' if is_mp_id else 'compositions'
        return '/'.join([
            self.preamble.rsplit('/', 1)[0], 'explorer', collection , doc['_id']
        ])

    def get_provenance(self):
        return self.get_global_hierarchical_data(self.provenance_keys)

    def get_global_hierarchical_data(self, keys):
        projection = {'_id': 1, 'mp_cat_id': 1}
        for key in keys:
            projection['content.' + key] = 1
        docs = self.query_contributions(projection=projection, limit=1)
        if not docs:
            raise Exception('No contributions found!')
        from mpcontribs.io.core.mpfile import MPFileCore
        mpfile = MPFileCore.from_contribution(docs[0])
        identifier = mpfile.ids[0]
        return mpfile.hdata[identifier]

    def get_material(self, identifier):
        docs = self.query_contributions(
            criteria={'mp_cat_id': identifier}, projection={'content': 1}
        )
        return docs[0] if docs else None

    def check_contributor(self):
        return self._make_request('/check_contributor')

    def submit_contribution(self, filename_or_mpfile, fmt):
        """
        Submit a MPFile containing contribution data to the Materials Project
        site. Only MPFiles with a single root-level section are allowed
        ("single contribution"). Don't use this function directly but rather go
        through the dedicated command line program `mgc` or through the
        web UI `MPFileViewer`.

        Args:
            filename_or_mpfile: MPFile name, or MPFile object
            fmt: archieml or custom

        Returns:
            unique contribution ID (ObjectID) for this submission

        Raises:
            MPResterError
        """
        try:
            if isinstance(filename_or_mpfile, six.string_types):
                with open(filename_or_mpfile, 'r') as f:
                    payload = {'mpfile': f.read()}
            else:
                payload = {'mpfile': filename_or_mpfile.get_string()}
            payload['fmt'] = fmt
        except Exception as ex:
            raise MPResterError(str(ex))
        return self._make_request('/submit', payload=payload, method='POST')

    def build_contribution(self, cid):
        """
        Build a contribution into the according material/composition on the
        Materials Project site.  Don't use this function directly but rather go
        through the dedicated command line program `mgc` or through the web UI
        `MPFileViewer`.

        Args:
            cid: ObjectId of contribution

        Raises:
            MPResterError
        """
        try:
            cid = bson.ObjectId(cid)
        except Exception as ex:
            raise MPResterError(str(ex))
        return self._make_request('/build', payload={'cid': cid}, method='POST')

    def query_contributions(self, **kwargs):
        """Query the contributions collection of the Materials Project site.

        Args:
            criteria (dict): Query criteria.
            contributor_only (bool): only show contributions for requesting contributor
            projection (dict): projection dict to reduce output
            collection (str): collection to query (contributions | materials | compositions)
            limit (int): number of documents to return

        Returns:
            A dict, with a list of contributions in the "response" key.

        Raises:
            MPResterError
        """
        if self.query is not None:
            if 'criteria' in kwargs:
                kwargs['criteria'].update(self.query)
            else:
                kwargs['criteria'] = self.query
        if kwargs:
            criteria = dict(kwargs.get('criteria', {}))
            payload = {
                "criteria": dumps(criteria),
                "contributor_only": dumps(kwargs.get('contributor_only', False)),
                "projection": dumps(kwargs.get('projection')),
                "collection": kwargs.get('collection', 'contributions'),
                "limit": kwargs.get('limit', 0)
            }
            docs = self._make_request('/query', payload=payload, method='POST')
        else:
            docs = self._make_request('/query')
        return docs

    def find_contribution(self, cid, as_doc=False, fmt='archieml'):
        """find a specific contribution"""
        mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
        MPFile = getattr(mod, 'MPFile')
        contrib = self.query_contributions(
            criteria={'_id': bson.ObjectId(cid)},
            projection={'_id': 0, 'mp_cat_id': 1, 'content': 1, 'collaborators': 1}
        )[0]
        if as_doc: return contrib
        return MPFile.from_contribution(contrib)

    def delete_contributions(self, cids=[]):
        """
        Delete a list of contributions from the Materials Project site.

        Args:
            cids (list): list of contribution IDs

        Returns:
            number of contributions deleted

        Raises:
            MPResterError
        """
        if not cids:
            cids = [c['_id'] for c in self.query_contributions()]
        payload = {"cids": dumps(cids)}
        return self._make_request('/delete', payload=payload, method='POST')

    def update_collaborators(self, collaborators, cids, mode):
        """
        Update collaborator for contributions to the Materials Project site.

        Args:
            collaborators (list): list of `FullNameInitial.LastName`
            cids (list): list of contribution IDs
            mode (str): add/remove/primary

        Returns:
            the updated list of collaborators for affected contributions

        Raises:
            MPResterError
        """
        try:
            payload = {
                'collaborators': dumps(collaborators),
                'cids': dumps(cids), 'mode': mode
            }
            response = self.session.post(
                "{}/contribs/collab".format(self.preamble), data=payload
            )
            if response.status_code in [200, 400]:
                resp = loads(response.text, cls=MPDecoder)
                if resp['valid_response']:
                    return resp['response']['collaborators']
                else:
                    raise MPResterError(resp["error"])
            raise MPResterError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPResterError(str(ex))

    def get_cif(self, cid, structure_name):
        return self._make_request('/cif/{}/{}'.format(cid, structure_name))

    def get_main_contributions(self, identifier):
        pass

    def get_card(self, cid='5956e310043b4b56b253e003',
        prov_keys=['title', 'url', 'explanation', 'references', 'authors', 'contributor']
    ):
        payload = {"provenance_keys": dumps(prov_keys)}
        return self._make_request('/card/'+cid, payload=payload, method='POST')
