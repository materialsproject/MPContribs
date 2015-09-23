# coding: utf-8
# https://github.com/materialsproject/pymatgen/blob/1eb2f2f/pymatgen/matproj/rest.py
from __future__ import division, unicode_literals
import os, requests, json, warnings, six, bson

class MPContribsRester(object):
    """
    A class to conveniently interface with the Materials Project REST interface
    when dealing with contributed data. The recommended way to use
    MPContribsRester is with the "with" context manager to ensure that sessions
    are properly closed after usage::

        with MPContribsRester("API_KEY") as m:
            do_something

    MPContribsRester uses the "requests" package, which provides for HTTP
    connection pooling. All connections are made via https for security.

    Args:
        api_key (str): A String API key for accessing the Materials Project
            REST interface. Please obtain your API key at
            https://www.materialsproject.org/dashboard. If this is None,
            the code will check if there is a "MAPI_KEY" environment variable
            set. If so, it will use that environment variable. This makes it
            easier for heavy users to simply add this environment variable to
            their setups and MPContribsRester can then be called without any arguments.
        endpoint (str): Url of endpoint to access the Materials Project REST
            interface. Defaults to the standard Materials Project REST
            address, but can be changed to other urls implementing a similar
            interface.
    """

    def __init__(self, api_key=None,
                 endpoint="https://www.materialsproject.org/rest/v2"):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("MAPI_KEY", "")
        self.preamble = endpoint
        self.session = requests.Session()
        self.session.headers = {"x-api-key": self.api_key}

    def __enter__(self):
        """Support for "with" context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support for "with" context."""
        self.session.close()

    def _make_request(self, sub_url, payload=None, method="GET"):
        response = None
        url = self.preamble + sub_url
        try:
            response = self.session.post(url, data=payload) if method == "POST" \
                        else self.session.get(url, params=payload)
            if response.status_code in [200, 400]:
                data = json.loads(response.text)
                if data["valid_response"]:
                    if data.get("warning"):
                        warnings.warn(data["warning"])
                    return data["response"]
                else:
                    raise MPContribsRestError(data["error"])
            raise MPContribsRestError(
                "REST query returned with error status code {}"
                .format(response.status_code)
            )
        except Exception as ex:
            msg = "{}. Content: {}".format(str(ex), response.content) \
                    if hasattr(response, "content") else str(ex)
            raise MPContribsRestError(msg)

    def check_contributor(self):
        return self._make_request('/contribs/check_contributor')

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
        return self._make_request('/contribs/submit', payload=payload, method='POST')

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
        return self._make_request('/contribs/build', payload={'cid': cid}, method='POST')

    def query_contributions(self, criteria=dict(), contributor_only=True,
                            projection=None, collection='contributions'):
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
        payload = {
            "criteria": json.dumps(criteria),
            "contributor_only": json.dumps(contributor_only),
            "projection": json.dumps(projection),
            "collection": json.dumps(collection)
        }
        return self._make_request('/contribs/query', payload=payload, method='POST')

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
            payload = {"cids": json.dumps(cids)}
            response = self.session.post(
                "{}/contribs/delete".format(self.preamble), data=payload
            )
            if response.status_code in [200, 400]:
                resp = json.loads(response.text, cls=MPDecoder)
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
                'collaborators': json.dumps(collaborators),
                'cids': json.dumps(cids), 'mode': mode
            }
            response = self.session.post(
                "{}/contribs/collab".format(self.preamble), data=payload
            )
            if response.status_code in [200, 400]:
                resp = json.loads(response.text, cls=MPDecoder)
                if resp['valid_response']:
                    return resp['response']['collaborators']
                else:
                    raise MPContribsRestError(resp["error"])
            raise MPContribsRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPContribsRestError(str(ex))

class MPContribsRestError(Exception):
    """
    Exception class for MPRestAdaptor.
    Raised when the query has problems, e.g., bad query format.
    """
    pass
