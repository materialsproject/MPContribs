# -*- coding: utf-8 -*-
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
                'PMG_MAPI_ENDPOINT', 'https://contribs.materialsproject.org/rest'
            )
        if test_site:
            # override api_key and endpoint with test_site values
            jpy_user = os.environ.get('JPY_USER')
            if not jpy_user:
                raise ValueError('Cannot connect to test_site outside MP JupyterHub!')
            flaskproxy = 'https://jupyterhub.materialsproject.org/flaskproxy'
            endpoint = '/'.join([flaskproxy, jpy_user, 'test_site/rest'])
            import webtzite.configure_settings
            import django
            django.setup()
            from webtzite.models import RegisteredUser
            try:
                u = RegisteredUser.objects.first()
            except RegisteredUser.DoesNotExist:
                login_url = '/'.join([flaskproxy, jpy_user, 'test_site'])
                raise ValueError('Visit {} to get registered first!'.format(login_url))
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
        return ["title", "authors", "description", "urls"]
        #raise NotImplementedError('Implement `provenance_keys` property in Rester!')

    @property
    def released(self):
        return False

    def _make_request(self, sub_url, payload=None, method="GET"):
        from mpcontribs.io.core.recdict import RecursiveDict
        return super(MPContribsRester, self)._make_request(
          '/'.join([sub_url, self.dbtype]), payload=payload, method=method,
          document_class=RecursiveDict
        )

    def get_cid_url(self, doc):
        """infer URL for contribution detail page from MongoDB doc"""
        from mpcontribs.config import mp_id_pattern
        is_mp_id = mp_id_pattern.match(doc['identifier'])
        collection = 'materials' if is_mp_id else 'compositions'
        return '/'.join([
            self.preamble.rsplit('/', 1)[0], 'explorer', collection , doc['_id']
        ])

    def get_provenance(self):
        return self.get_global_hierarchical_data(self.provenance_keys)

    def get_global_hierarchical_data(self, keys):
        projection = {'_id': 0, 'project': 0}
        for key in keys:
            projection[key] = 1
        docs = self.query_contributions(projection=projection, collection='provenances')
        if not docs:
            raise Exception('No contributions found!')
        #from mpcontribs.io.core.mpfile import MPFileCore
        #mpfile = MPFileCore.from_dict(docs[0])
        #identifier = mpfile.ids[0]
        #return mpfile.hdata[identifier]
        docs[0].pop('_id')
        docs[0].pop('project')
        return docs[0]

    def get_material(self, identifier):
        docs = self.query_contributions(
            criteria={'identifier': identifier}, projection={'content': 1}
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
        web UI `MPContribs Ingester`.

        Args:
            filename_or_mpfile: MPFile name, or MPFile object
            fmt: archieml

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

    def find_contribution(self, cid, as_doc=False, fmt='archieml'):
        """find a specific contribution"""
        projection = {'identifier': 1, 'content': 1, 'collaborators': 1, 'project': 1}
        contrib = self.query_contributions(
            criteria={'_id': bson.ObjectId(cid)}, projection=projection
        )[0]
        if as_doc:
            return contrib
        mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
        MPFile = getattr(mod, 'MPFile')
        return MPFile.from_contribution(contrib)
