# coding: utf-8
# https://github.com/materialsproject/pymatgen/blob/1eb2f2f/pymatgen/matproj/rest.py
from __future__ import division, unicode_literals
import os, requests, json, warnings

class MPRester(object):
    """
    A class to conveniently interface with the Materials Project REST
    interface. The recommended way to use MPRester is with the "with" context
    manager to ensure that sessions are properly closed after usage::

        with MPRester("API_KEY") as m:
            do_something

    MPRester uses the "requests" package, which provides for HTTP connection
    pooling. All connections are made via https for security.

    .. note::

        The Materials Project recently switched to using string ids with a
        "mp-" prefix for greater flexibility going forward. The MPRester
        should still work as intended if you provide the proper string ids.

    Args:
        api_key (str): A String API key for accessing the MaterialsProject
            REST interface. Please obtain your API key at
            https://www.materialsproject.org/dashboard. If this is None,
            the code will check if there is a "MAPI_KEY" environment variable
            set. If so, it will use that environment variable. This makes
            easier for heavy users to simply add this environment variable to
            their setups and MPRester can then be called without any arguments.
        endpoint (str): Url of endpoint to access the MaterialsProject REST
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
        """
        Support for "with" context.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Support for "with" context.
        """
        self.session.close()

    def _make_request(self, sub_url, payload=None, method="GET",
                      mp_decode=True):
        response = None
        url = self.preamble + sub_url
        try:
            if method == "POST":
                response = self.session.post(url, data=payload)
            else:
                response = self.session.get(url, params=payload)
            if response.status_code in [200, 400]:
                data = json.loads(response.text)
                if data["valid_response"]:
                    if data.get("warning"):
                        warnings.warn(data["warning"])
                    return data["response"]
                else:
                    raise MPRestError(data["error"])

            raise MPRestError("REST query returned with error status code {}"
                              .format(response.status_code))

        except Exception as ex:
            msg = "{}. Content: {}".format(str(ex), response.content)\
                if hasattr(response, "content") else str(ex)
            raise MPRestError(msg)

    def submit_mpfile(self, filename, cids=None):
        """
        Submit a MPFile containing contribution data to the Materials Project site.

        Args:
            filename: name of MPFile
            cids: list of contribution IDs to be updated using this MPFile

        Returns:
            unique contribution IDs for this submission

        Raises:
            MPRestError
        """
        try:
            if not isinstance(filename, string_types):
                raise MPRestError("Provide name of MPFile.")
            with open(filename, 'r') as f:
                payload = {'mpfile': f.read()}
                if cids is not None: payload['cids'] = json.dumps(cids)
                response = self.session.post(
                    '{}/mpfile/submit'.format(self.preamble), data=payload
                )
                if response.status_code in [200, 400]:
                    resp = json.loads(response.text, cls=MPDecoder)
                    if resp['valid_response']:
                        return resp['contribution_ids']
                    else:
                        raise MPRestError(resp["error"])
                raise MPRestError("REST error with status code {} and error {}"
                                  .format(response.status_code, response.text))
        except Exception as ex:
            raise MPRestError(str(ex))

    def query_contribs(self, criteria=dict(), contributor_only=True):
        """
        Query the contributions collection of the Materials Project site.

        Args:
            criteria (dict): Query criteria.
            contributor_only (bool): only show contributions for requesting contributor

        Returns:
            A dict, with a list of contributions in the "response" key.

        Raises:
            MPRestError
        """
        try:
            payload = {
                "criteria": json.dumps(criteria),
                "contributor_only": json.dumps(contributor_only)
            }
            response = self.session.post(
                "{}/contribs/query".format(self.preamble), data=payload
            )
            if response.status_code in [200, 400]:
                resp = json.loads(response.text, cls=MPDecoder)
                if resp['valid_response']:
                    return resp['response']
                else:
                    raise MPRestError(resp["error"])
            raise MPRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPRestError(str(ex))

    def delete_contribs(self, cids):
        """
        Delete a list of contributions from the Materials Project site.

        Args:
            cids (list): list of contribution IDs

        Returns:
            number of contributions deleted

        Raises:
            MPRestError
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
                    raise MPRestError(resp["error"])
            raise MPRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPRestError(str(ex))

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
            MPRestError
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
                    raise MPRestError(resp["error"])
            raise MPRestError("REST error with status code {} and error {}"
                              .format(response.status_code, response.text))
        except Exception as ex:
            raise MPRestError(str(ex))

class MPRestError(Exception):
    """
    Exception class for MPRestAdaptor.
    Raised when the query has problems, e.g., bad query format.
    """
    pass
