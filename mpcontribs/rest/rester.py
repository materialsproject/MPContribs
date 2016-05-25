from __future__ import division, unicode_literals
import six, bson
from bson.json_util import dumps, loads
from mpweb_core.rester import MPResterBase, MPResterError
from mpcontribs.io.core.mpfile import MPFileCore

class MPContribsRester(MPResterBase):
    """convenience functions to interact with MPContribs REST interface"""
    def __init__(self, api_key=None,
                 endpoint="https://www.materialsproject.org/mpcontribs/rest",
                 dbtype='read'):
        # TODO set endpoint automatically based on host or parent django app?
        super(MPContribsRester, self).__init__(
          api_key=api_key, endpoint=endpoint
        )
        self.dbtype = dbtype

    def _make_request(self, sub_url, payload=None, method="GET"):
        return super(MPContribsRester, self)._make_request(
          '/'.join([sub_url, self.dbtype]), payload=payload, method=method
        )

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
            MPContribsRestError
        """
        try:
            if isinstance(filename_or_mpfile, six.string_types):
                with open(filename_or_mpfile, 'r') as f:
                    payload = {'mpfile': f.read()}
            else:
                payload = {'mpfile': filename_or_mpfile.get_string()}
            payload['fmt'] = fmt
        except Exception as ex:
            raise MPContribsRestError(str(ex))
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
            MPContribsRestError
        """
        try:
            cid = bson.ObjectId(cid)
        except Exception as ex:
            raise MPContribsRestError(str(ex))
        return self._make_request('/build', payload={'cid': cid}, method='POST')

    def query_contributions(self, **kwargs):
        """Query the contributions collection of the Materials Project site.

        Args:
            criteria (dict): Query criteria.
            contributor_only (bool): only show contributions for requesting contributor
            projection (dict): projection dict to reduce output
            collection (str): collection to query (contributions | materials | compositions)

        Returns:
            A dict, with a list of contributions in the "response" key.

        Raises:
            MPContribsRestError
        """
        if kwargs:
            payload = {
                "criteria": dumps(kwargs.get('criteria', {})),
                "contributor_only": dumps(kwargs.get('contributor_only', False)),
                "projection": dumps(kwargs.get('projection')),
                "collection": kwargs.get('collection', 'contributions')
            }
            docs = self._make_request('/query', payload=payload, method='POST')
        else:
            docs = self._make_request('/query')
        return docs if len(docs) != 1 else docs[0]

    def find_contribution(self, cid, as_doc=False):
        """find a specific contribution"""
        contrib = self.query_contributions(
            criteria={'_id': bson.ObjectId(cid)},
            projection={'_id': 0, 'mp_cat_id': 1, 'content': 1, 'collaborators': 1}
        )
        if as_doc: return contrib
        return MPFileCore.from_contribution(contrib)

    def delete_contributions(self, cids):
        """
        Delete a list of contributions from the Materials Project site.

        Args:
            cids (list): list of contribution IDs

        Returns:
            number of contributions deleted

        Raises:
            MPContribsRestError
        """
        try:
            payload = {"cids": dumps(cids)}
            response = self.session.post(
                "{}/contribs/delete".format(self.preamble), data=payload
            )
            if response.status_code in [200, 400]:
                resp = loads(response.text, cls=MPDecoder)
                if resp['valid_response']:
                    return resp['response']['n']
                else:
                    raise MPContribsRestError(resp["error"])
            raise MPContribsRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPContribsRestError(str(ex))

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
            MPContribsRestError
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
                    raise MPContribsRestError(resp["error"])
            raise MPContribsRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPContribsRestError(str(ex))
