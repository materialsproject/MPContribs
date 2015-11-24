# coding: utf-8
# https://github.com/materialsproject/pymatgen/blob/1eb2f2f/pymatgen/matproj/rest.py
from __future__ import division, unicode_literals
import os, requests, json, warnings, urlparse

class MPResterBase(object):
    """
    A base class to conveniently interface with a REST interface in the style of
    the Materials Project. For your own "rester", inherit from MPResterBase and
    add convenience functions which return the result of HTTP requests via
    `MPResterBase._make_request(<URL>, ..)`. The recommended way to use the
    resulting `MPCustomRester` is with the "with" context manager to ensure that
    sessions are properly closed after usage::

        with MPCustomRester("API_KEY") as m:
            m.do_something()

    MPResterBase uses the "requests" package, which provides for HTTP connection
    pooling.

    Args:
        api_key (str): A String API key for accessing the REST interface. If
            this is None, the code will check if there is a "MAPI_KEY"
            environment variable set. If so, it will use that environment
            variable. This makes it easier for heavy users to simply add this
            environment variable to their setups and MPResterBase can then be
            called without any arguments.
        endpoint (str): URL of endpoint to access the REST interface. Defaults
            to the standard Materials Project REST address, but can be changed
            to other urls implementing a similar interface.
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
            if self.session.cookies.get('csrftoken') is None:
                from django.core.urlresolvers import reverse
                uri = urlparse.urlparse(self.preamble)
                domain = '{uri.scheme}://{uri.netloc}/'.format(uri=uri)
                domain += uri.path.split('/')[1] # test_site/
                domain += reverse('browserid.csrf')
                self.session.get(domain)
            headers = {"X-CSRFToken": self.session.cookies.get('csrftoken')}
            response = self.session.post(url, data=payload, headers=headers) \
                if method == "POST" else self.session.get(url, params=payload)
            if response.status_code in [200, 400]:
                data = json.loads(response.text)
                if data["valid_response"]:
                    if data.get("warning"):
                        warnings.warn(data["warning"])
                    return data["response"]
                else:
                    raise MPResterError(data["error"])
            raise MPResterError(
                "REST query returned with error status code {}"
                .format(response.status_code)
            )
        except Exception as ex:
            msg = "{}. Content: {}".format(str(ex), repr(response.content)) \
                    if hasattr(response, "content") else str(ex)
            raise MPResterError(msg)

class MPResterError(Exception):
    """
    Exception class for MPResterBase.
    Raised when the query has problems, e.g., bad query format.
    """
    pass
