# coding: utf-8
# https://github.com/materialsproject/pymatgen/blob/1eb2f2f/pymatgen/matproj/rest.py
from __future__ import division, unicode_literals
import os, requests, warnings, urlparse
from bson.json_util import loads, JSONOptions
from collections import OrderedDict
import webtzite.configure_settings
import django
django.setup()

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
    def __init__(self, api_key=None, endpoint=None):
        if api_key is None or endpoint is None:
            try:
                from pymatgen import SETTINGS
            except ImportError:
                warnings.warn('MPResterBase: not using pymatgen SETTINGS!')
                SETTINGS = {}
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = SETTINGS.get("PMG_MAPI_KEY", "")
        if endpoint is not None:
            self.preamble = endpoint
        else:
            self.preamble = SETTINGS.get(
                "PMG_MAPI_ENDPOINT", "https://www.materialsproject.org/rest/v2"
            )
        if not self.api_key:
            raise ValueError('API key not set. Run `pmg config --add PMG_MAPI_KEY <USER_API_KEY>`.')
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
        url = self.preamble.replace('8000', '5000') + sub_url
        try:
            headers = {'Referer': self.preamble}
            if self.session.cookies.get('csrftoken') is None:
                from django.core.urlresolvers import reverse
                uri = urlparse.urlparse(self.preamble)
                domain = '{uri.scheme}://{uri.netloc}'.format(uri=uri).replace('8000', '5000')
                site_url = '/'.join(uri.path.split('/')[:-2]) # test_site/
                browserid_csrf = reverse('browserid.csrf')
                if site_url[:-1] not in browserid_csrf:
                    domain += site_url
                domain += browserid_csrf
                self.session.get(domain)
            headers["X-CSRFToken"] = self.session.cookies.get('csrftoken')
            response = self.session.request(method, url=url, headers=headers, data=payload)
            if response.status_code in [200, 400]:
                data = loads(response.text, json_options=JSONOptions(document_class=OrderedDict))
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
