# -*- coding: utf-8 -*-
import os
import json
import fido
import warnings
import pandas as pd

try:
    from tqdm.notebook import tqdm
except ImportError:
    from tqdm import tqdm

from hashlib import md5
from copy import deepcopy
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
from concurrent.futures import as_completed
from requests_futures.sessions import FuturesSession


DEFAULT_HOST = "api.mpcontribs.org"
BULMA = "is-narrow is-fullwidth has-background-light"

j2h = Json2Html()
pd.options.plotting.backend = "plotly"
warnings.formatwarning = lambda msg, *args, **kwargs: f"{msg}\n"
warnings.filterwarnings("default", category=DeprecationWarning, module=__name__)


def get_md5(d):
    s = json.dumps(d, sort_keys=True).encode("utf-8")
    return md5(s).hexdigest()


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


def chunks(lst, n=250):
    n = max(1, n)
    for i in range(0, len(lst), n):
        to = i + n
        yield lst[i:to]


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
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return True


class Dict(dict):
    def pretty(self, attrs=f'class="table {BULMA}"'):
        return display(
            HTML(j2h.convert(json=remap(self, visit=visit), table_attributes=attrs))
        )


def load_client(apikey=None, headers=None, host=None):
    warnings.warn(
        "load_client(...) is deprecated, use Client(...) instead", DeprecationWarning
    )


class Client(SwaggerClient):
    """client to connect to MPContribs API

    We only want to load the swagger spec from the remote server when needed and not everytime the
    client is initialized. Hence using the Borg design nonpattern (instead of Singleton): Since the
    __dict__ of any instance can be re-bound, Borg rebinds it in its __init__ to a class-attribute
    dictionary. Now, any reference or binding of an instance attribute will actually affect all
    instances equally.
    """

    _shared_state = {}

    def __init__(self, apikey=None, headers=None, host=None):
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost
        self.__dict__ = self._shared_state

        if not host:
            host = os.environ.get("MPCONTRIBS_API_HOST", DEFAULT_HOST)

        if not apikey:
            apikey = os.environ.get("MPCONTRIBS_API_KEY")

        if apikey and headers is not None:
            apikey = None
            warnings.warn("headers set => ignoring apikey!")

        self.apikey = apikey
        self.headers = {"x-api-key": apikey} if apikey else headers
        self.host = host
        self.protocol = "https" if self.apikey else "http"
        self.url = f"{self.protocol}://{self.host}"

        if "swagger_spec" not in self.__dict__ or (
            self.headers is not None
            and self.swagger_spec.http_client.headers != self.headers
        ):
            self.load()

    def load(self):
        http_client = FidoClientGlobalHeaders(headers=self.headers)
        loader = Loader(http_client)
        origin_url = f"{self.url}/apispec.json"
        spec_dict = loader.load_spec(origin_url)
        spec_dict["host"] = self.host
        spec_dict["schemes"] = [self.protocol]

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

        # expand regex-based query parameters for `data` columns
        try:
            resp = self.projects.get_entries(_fields=["columns"]).result()
        except AttributeError:
            # skip in tests
            return

        columns = {"text": [], "number": []}
        for project in resp["data"]:
            for column in project["columns"]:
                if column["path"].startswith("data."):
                    col = column["path"].replace(".", "__")
                    if column["unit"] == "NaN":
                        columns["text"].append(col)
                    else:
                        col = f"{col}__value"
                        columns["number"].append(col)

        operators = {"text": ["contains"], "number": ["gte", "lte"]}
        for path, d in spec_dict["paths"].items():
            for verb in ["get", "put", "post", "delete"]:
                if verb in d:
                    old_params = deepcopy(d[verb].pop("parameters"))
                    new_params, param_names = [], set()

                    while old_params:
                        param = old_params.pop()
                        if param["name"].startswith("^data__"):
                            op = param["name"].rsplit("__", 1)[1]
                            for typ, ops in operators.items():
                                if op in ops:
                                    for column in columns[typ]:
                                        new_param = deepcopy(param)
                                        param_name = f"{column}__{op}"
                                        if param_name not in param_names:
                                            new_param["name"] = param_name
                                            desc = f"filter {column} via ${op}"
                                            new_param["description"] = desc
                                            new_params.append(new_param)
                                            param_names.add(param_name)
                        else:
                            new_params.append(param)

                    d[verb]["parameters"] = new_params

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
        )  # don't return dynamic fields (card_*)
        return Dict(self.contributions.get_entry(pk=cid, _fields=fields).result())

    def get_table(self, tid):
        """Convenience function to get full Pandas DataFrame for a table."""
        table = {"data": []}
        page, pages = 1, None

        while pages is None or page <= pages:
            resp = self.tables.get_entry(
                pk=tid, _fields=["_all"], data_page=page, data_per_page=1000
            ).result()
            table["data"].extend(resp["data"])
            if pages is None:
                pages = resp["total_data_pages"]
                table["columns"] = resp["columns"]
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

    def delete_contributions(self, project, per_page=100):
        """Convenience function to remove all contributions for a project"""
        resp = self.contributions.get_entries(
            project=project, per_page=per_page, _fields=["id"]
        ).result()
        cids = [d["id"] for d in resp["data"]]  # in first page
        ncontribs = resp["total_count"]

        if cids:
            with tqdm(total=ncontribs) as pbar:
                with FuturesSession(max_workers=10) as session:
                    # bravado future unfortunately doesn't work with concurrent.futures
                    pbar.set_description("Get contribution IDs")
                    endpoint = f"{self.url}/contributions/"
                    pages = resp["total_pages"]
                    futures = [
                        session.get(
                            endpoint,
                            headers=self.headers,
                            params={
                                "project": project,
                                "_fields": "id",
                                "page": page,
                                "per_page": per_page,
                            },
                        )
                        for page in range(2, pages + 1)
                    ]

                    for future in as_completed(futures):
                        response = future.result()
                        status = response.status_code
                        if status in [200, 400, 401, 404, 500]:
                            resp = response.json()
                            if status == 200:
                                cids += [d["id"] for d in resp["data"]]
                                pbar.update(len(resp["data"]))
                            else:
                                warnings.warn(resp["error"])
                        else:
                            warnings.warn(response.content.decode("utf-8"))

                    pbar.refresh()
                    pbar.set_description("Delete contribution(s)")
                    futures = [
                        session.delete(
                            endpoint,
                            headers=self.headers,
                            params={
                                "project": project,
                                "id__in": ",".join(chunk),
                                "per_page": per_page,
                            },
                        )
                        for chunk in chunks(cids, n=per_page)
                    ]

                    resp = None
                    for future in as_completed(futures):
                        response = future.result()
                        status = response.status_code
                        if status in [200, 400, 401, 404, 500]:
                            resp = response.json()
                            if status == 200:
                                pbar.update(resp["count"])
                            else:
                                warnings.warn(resp["error"])
                        else:
                            warnings.warn(response.content.decode("utf-8"))

                    if resp and resp.get("count"):
                        self.load()

    def submit_contributions(
        self, contributions, skip_dupe_check=False, ignore_dupes=False, per_page=100
    ):
        """Convenience function to submit a list of contributions"""
        # prepare structures/tables
        with tqdm(total=len(contributions)) as pbar:
            existing = {
                "ids": set(),
                "identifiers": set(),
                "structures": set(),
                "tables": set(),
            }
            unique_identifiers = True
            endpoint = f"{self.url}/contributions/"

            if not skip_dupe_check:
                name = contributions[0]["project"]
                resp = self.projects.get_entry(
                    pk=name, _fields=["unique_identifiers"]
                ).result()
                unique_identifiers = resp["unique_identifiers"]

                pbar.set_description("Get existing contribution(s)")
                resp = self.contributions.get_entries(
                    project=name, per_page=per_page, _fields=["id"],
                ).result()
                pages = resp["total_pages"]

                with FuturesSession(max_workers=10) as session:
                    # bravado future unfortunately doesn't work with concurrent.futures
                    futures = [
                        session.get(
                            endpoint,
                            headers=self.headers,
                            params={
                                "project": name,
                                "page": page + 1,
                                "per_page": per_page,
                                "_fields": "id,identifier,structures,tables",
                            },
                        )
                        for page in range(pages)
                    ]

                    for future in as_completed(futures):
                        response = future.result()
                        status = response.status_code
                        if status in [200, 400, 401, 404, 500]:
                            resp = response.json()
                            if status == 200:
                                for contrib in resp["data"]:
                                    existing["ids"].add(contrib["id"])
                                    existing["identifiers"].add(contrib["identifier"])

                                    for component in ["structures", "tables"]:
                                        md5s = set(d["md5"] for d in contrib[component])
                                        existing[component] |= md5s

                                    pbar.update(1)
                            else:
                                warnings.warn(resp["error"])
                        else:
                            warnings.warn(response.content.decode("utf-8"))

                nexisting = 0
                if unique_identifiers and existing["identifiers"]:
                    nexisting = len(existing["identifiers"])
                elif existing["ids"]:
                    nexisting = len(existing["ids"])

                if nexisting:
                    print(f"{nexisting} contributions already submitted.")

                pbar.refresh()

            contribs = []
            digests = {"structures": set(), "tables": set()}
            pbar.set_description("Prepare contribution(s)")

            # TODO parallelize?
            for contrib in contributions:

                if (
                    unique_identifiers
                    and contrib["identifier"] in existing["identifiers"]
                ):
                    pbar.update(1)
                    continue

                contribs.append(deepcopy(contrib))

                for component in digests.keys():
                    comp_list = contribs[-1].pop(component, [])
                    contribs[-1][component] = []

                    for idx, element in enumerate(comp_list):
                        is_structure = isinstance(element, Structure)
                        if component == "structures" and not is_structure:
                            raise ValueError("Only accepting pymatgen Structure!")
                        elif component == "tables" and not isinstance(
                            element, pd.DataFrame
                        ):
                            raise ValueError("Only accepting pandas DataFrame!")

                        if is_structure:
                            dct = element.as_dict()
                            del dct["@module"]
                            del dct["@class"]

                            if not dct.get("charge"):
                                del dct["charge"]
                        else:
                            for col in element.columns:
                                element[col] = element[col].astype(str)
                            dct = element.to_dict(orient="split")
                            del dct["index"]

                        digest = get_md5(dct)

                        if is_structure:
                            c = element.composition
                            comp = c.get_integer_formula_and_factor()
                            dct["name"] = f"{comp[0]}-{idx}"
                        else:
                            name = element.index.name
                            dct["name"] = name if name else f"table-{idx}"

                        dupe = (
                            digest in digests[component]
                            or digest in existing[component]
                        )

                        if not ignore_dupes and dupe:
                            msg = f"Duplicate: {dct['name']}!"
                            raise ValueError(msg)

                        if not dupe:
                            digests[component].add(digest)
                            contribs[-1][component].append(dct)

                pbar.update(1)

            ncontribs = len(contribs)

            if ncontribs:
                pbar.refresh()
                pbar.reset(total=ncontribs)
                pbar.set_description("Submit contribution(s)")
                resp = None

                with FuturesSession(max_workers=10) as session:
                    # bravado future unfortunately doesn't work with concurrent.futures
                    headers = {"Content-Type": "application/json"}
                    headers.update(self.headers)
                    futures = [
                        session.post(
                            endpoint,
                            headers=headers,
                            data=json.dumps(chunk).encode("utf-8"),
                        )
                        for chunk in chunks(contribs, n=per_page)
                    ]

                    for future in as_completed(futures):
                        response = future.result()
                        status = response.status_code
                        if status in [201, 400, 401, 404, 500]:
                            resp = response.json()
                            if status == 201:
                                pbar.update(resp["count"])
                            else:
                                warnings.warn(resp["error"])
                        else:
                            warnings.warn(response.content.decode("utf-8"))

                    if resp and resp.get("count"):
                        self.load()
