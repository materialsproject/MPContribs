# -*- coding: utf-8 -*-
import os
import fido
import warnings
import pandas as pd

from urllib.parse import urlparse
from pyisemail import is_email
from pyisemail.diagnosis import BaseDiagnosis
from swagger_spec_validator.common import SwaggerValidationError
from bravado_core.formatter import SwaggerFormat
from bravado.client import SwaggerClient
from bravado.fido_client import FidoClient  # async
from bravado.http_future import HttpFuture
from bravado.swagger_model import Loader
from bravado.config import bravado_config_from_config_dict
from bravado_core.spec import Spec
from json2html import Json2Html
from IPython.display import display, HTML
from boltons.iterutils import remap
from pymatgen import Structure


DEFAULT_HOST = "api.mpcontribs.org"
HOST = os.environ.get("MPCONTRIBS_API_HOST", DEFAULT_HOST)
BULMA = "is-narrow is-fullwidth has-background-light"

j2h = Json2Html()
quantity_keys = {"display", "value", "unit"}
pd.options.plotting.backend = "plotly"
warnings.formatwarning = lambda msg, *args, **kwargs: f"{msg}\n"
warnings.filterwarnings("default", category=DeprecationWarning, module=__name__)


def validate_email(email_string):
    d = is_email(email_string, diagnose=True)
    if d > BaseDiagnosis.CATEGORIES["VALID"]:
        raise SwaggerValidationError(f"{email_string} {d.message}")


email_format = SwaggerFormat(
    format="email",
    to_wire=str,
    to_python=str,
    validate=validate_email,
    description="e-mail address",
)


def validate_url(url_string, qualifying=("scheme", "netloc")):
    tokens = urlparse(url_string)
    if not all([getattr(tokens, qual_attr) for qual_attr in qualifying]):
        raise SwaggerValidationError(f"{url_string} invalid")


url_format = SwaggerFormat(
    format="url", to_wire=str, to_python=str, validate=validate_url, description="URL",
)


class FidoClientGlobalHeaders(FidoClient):
    def __init__(self, headers=None):
        super().__init__()
        self.headers = headers or {}

    def request(self, request_params, operation=None, request_config=None):
        request_for_twisted = self.prepare_request_for_twisted(request_params)
        request_for_twisted["headers"].update(self.headers)
        future_adapter = self.future_adapter_class(fido.fetch(**request_for_twisted))
        return HttpFuture(
            future_adapter, self.response_adapter_class, operation, request_config
        )


def visit(path, key, value):
    if isinstance(value, dict) and quantity_keys == set(value.keys()):
        return key, value["display"]
    return True


class Dict(dict):
    def pretty(self, attrs=f'class="table {BULMA}"'):
        return display(
            HTML(j2h.convert(json=remap(self, visit=visit), table_attributes=attrs))
        )


def load_client(apikey=None, headers=None, host=HOST):
    warnings.warn(
        "load_client(...) is deprecated, use Client(...) instead", DeprecationWarning
    )


# TODO data__ regex doesn't work through bravado/swagger client
class Client(SwaggerClient):
    """client to connect to MPContribs API

    We only want to load the swagger spec from the remote server when needed and not everytime the
    client is initialized. Hence using the Borg design nonpattern (instead of Singleton): Since the
    __dict__ of any instance can be re-bound, Borg rebinds it in its __init__ to a class-attribute
    dictionary. Now, any reference or binding of an instance attribute will actually affect all
    instances equally.
    """

    _shared_state = {}

    def __init__(self, apikey=None, headers=None, host=HOST):
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost
        self.__dict__ = self._shared_state
        self.apikey = apikey
        self.headers = {"x-api-key": apikey} if apikey else headers
        self.host = host

        if "swagger_spec" not in self.__dict__ or (
            self.headers is not None
            and self.swagger_spec.http_client.headers != self.headers
        ):
            http_client = FidoClientGlobalHeaders(headers=self.headers)
            loader = Loader(http_client)
            protocol = "https" if self.apikey else "http"
            origin_url = f"{protocol}://{self.host}/apispec.json"
            spec_dict = loader.load_spec(origin_url)
            spec_dict["host"] = self.host
            spec_dict["schemes"] = [protocol]

            config = {
                "validate_responses": False,
                "use_models": False,
                "include_missing_properties": False,
                "formats": [email_format, url_format],
            }
            bravado_config = bravado_config_from_config_dict(config)
            for key in set(bravado_config._fields).intersection(set(config)):
                del config[key]
            config["bravado"] = bravado_config

            swagger_spec = Spec.from_dict(spec_dict, origin_url, http_client, config)
            super().__init__(
                swagger_spec, also_return_response=bravado_config.also_return_response
            )

    def get_project(self, project):
        """Convenience function to get full project entry and display as HTML table"""
        return Dict(self.projects.get_entry(pk=project, _fields=["_all"]).result())

    def get_contribution(self, cid):
        """Convenience function to get full contribution entry and display as HTML table"""
        fields = list(
            self.swagger_spec.definitions.get("ContributionsSchema")._properties.keys()
        )
        fields.remove("notebook")
        return Dict(self.contributions.get_entry(pk=cid, _fields=fields).result())

    def get_table(self, tid):
        """Convenience function to get full Pandas DataFrame for a table."""
        page, pages = 1, None
        table = {"data": []}

        while pages is None or page <= pages:
            res = self.tables.get_entry(
                pk=tid, _fields=["_all"], data_page=page, data_per_page=1000
            ).result()

            if "columns" not in table:
                pages = res["total_data_pages"]
                table["columns"] = res["columns"]

            table["data"].extend(res["data"])
            page += 1

        return pd.DataFrame.from_records(
            table["data"], columns=table["columns"], index=table["columns"][0]
        )

    def get_structure(self, sid):
        """Convenience function to get pymatgen structure."""
        return Structure.from_dict(
            self.structures.get_entry(
                pk=sid, _fields=["lattice", "sites", "charge"]
            ).result()
        )
