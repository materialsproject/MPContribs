# -*- coding: utf-8 -*-
import os
import json
import fido
import time
import warnings
import pandas as pd
import plotly.io as pio

try:
    from tqdm.notebook import tqdm
except ImportError:
    from tqdm import tqdm

from hashlib import md5
from copy import deepcopy
from urllib.parse import urlparse
from pyisemail import is_email
from collections import defaultdict
from ratelimit import limits, sleep_and_retry
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


MAX_WORKERS = 10
DEFAULT_HOST = "contribs-api.materialsproject.org"
BULMA = "is-narrow is-fullwidth has-background-light"

j2h = Json2Html()
pd.options.plotting.backend = "plotly"
pio.templates.default = "simple_white"
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
    if isinstance(lst, set):
        lst = list(lst)
    elif not isinstance(lst, list):
        raise ValueError("chunks needs list or set as input")

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
            print("headers set => ignoring apikey!")

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
        fields.remove("notebook")
        return Dict(self.contributions.get_entry(pk=cid, _fields=fields).result())

    def get_table(self, tid_or_md5):
        """Convenience function to get full Pandas DataFrame for a table.

        Args:
            tid_or_md5 (str): ObjectId or MD5 hash digest for table

        Returns:
            pd.DataFrame: pandas DataFrame containing table data
        """
        str_len = len(tid_or_md5)
        if str_len not in {24, 32}:
            raise ValueError(f"'{tid_or_md5}' is not a valid table id or md5 hash digest!")

        if str_len == 32:
            tables = self.tables.get_entries(md5=tid_or_md5, _fields=["id"]).result()
            if not tables:
                raise ValueError(f"table for md5 '{tid_or_md5}' not found!")
            tid = tables["data"][0]["id"]
        else:
            tid = tid_or_md5

        table = {"data": []}
        page, pages = 1, None

        while pages is None or page <= pages:
            resp = self.tables.get_entry(
                pk=tid, _fields=["_all"], data_page=page, data_per_page=1000
            ).result()
            table["data"].extend(resp["data"])
            if pages is None:
                pages = resp["total_data_pages"]
                table["attrs"] = resp["attrs"]
                table["index"] = resp["index"]
                table["columns"] = resp["columns"]
            page += 1

        df = pd.DataFrame.from_records(
            table["data"], columns=table["columns"], index=table["index"]
        )
        df.attrs = table["attrs"]
        labels = table["attrs"].get("labels", {})

        if "index" in labels:
            df.index.name = labels["index"]
        if "variable" in labels:
            df.columns.name = labels["variable"]

        return df

    def get_structure(self, sid):
        """Convenience function to get pymatgen structure."""
        return Structure.from_dict(
            self.structures.get_entry(
                pk=sid, _fields=["lattice", "sites", "charge"]
            ).result()
        )

    def init_columns(self, project, columns):
        """initialize columns to set their order and desired units"""
        self.projects.update_entry(pk=project, project={"columns": []}).result()
        cols = []

        for path, unit in columns.items():
            col = {"path": f"data.{path}"}
            if unit is not None:
                col["unit"] = unit

            cols.append(col)

        return self.projects.update_entry(
            pk=project, project={"columns": cols}
        ).result()

    def delete_contributions(self, project, per_page=100, max_workers=5):
        """Convenience function to remove all contributions for a project"""
        tic = time.perf_counter()

        if max_workers > MAX_WORKERS:
            max_workers = MAX_WORKERS
            print(f"max_workers reset to max {MAX_WORKERS}")

        cids = self.get_contributions(project)["ids"]
        total = len(cids)

        if cids:
            with FuturesSession(max_workers=max_workers) as session:
                while cids:
                    futures = [
                        session.delete(
                            f"{self.url}/contributions/",
                            headers=self.headers,
                            params={
                                "project": project,
                                "id__in": ",".join(chunk),
                                "per_page": per_page,
                            },
                        )
                        for chunk in chunks(cids, n=per_page)
                    ]

                    self._run_futures(futures, total=len(cids))
                    cids = self.get_contributions(project)["ids"]

                self.load()

        # reset columns to be save (sometimes not all are reset BUGFIX?)
        self.projects.update_entry(pk=project, project={"columns": []}).result()
        toc = time.perf_counter()
        dt = (toc - tic) / 60
        print(f"It took {dt:.1f}min to delete {total} contributions.")

    # TODO ratelimit support in bravado (wrapped around get_entry..., monkey-patch?)
    @sleep_and_retry
    @limits(calls=175, period=60)
    def get_unique_identifiers_flag(self, name):
        return self.projects.get_entry(
            pk=name, _fields=["unique_identifiers"]
        ).result()["unique_identifiers"]

    @sleep_and_retry
    @limits(calls=175, period=60)
    def get_total_pages(self, name, per_page):
        return self.contributions.get_entries(
            project=name, per_page=per_page, _fields=["id"],
        ).result()["total_pages"]

    def get_contributions(self, name):
        """get list of existing contributions"""
        ret = defaultdict(set)
        ret["unique_identifiers"] = self.get_unique_identifiers_flag(name)
        pages = self.get_total_pages(name, 250)

        @sleep_and_retry
        @limits(calls=175, period=60)
        def get_future(page):
            future = session.get(
                f"{self.url}/contributions/",
                headers=self.headers,
                params={
                    "project": name,
                    "page": page,
                    "per_page": 250,
                    "_fields": "id,identifier,structures,tables",
                },
            )
            setattr(future, "track_id", page)
            return future

        with FuturesSession(max_workers=MAX_WORKERS) as session:
            # bravado future doesn't work with concurrent.futures
            futures = [get_future(page + 1) for page in range(pages)]

            while futures:
                responses = self._run_futures(futures)

                for resp in responses.values():
                    for contrib in resp["data"]:
                        ret["ids"].add(contrib["id"])
                        ret["identifiers"].add(contrib["identifier"])

                        for component in ["structures", "tables"]:
                            md5s = set(d["md5"] for d in contrib[component])
                            ret[component] |= md5s

                futures = [
                    future
                    for future in futures
                    if future.track_id not in responses.keys()
                ]

        return ret

    def submit_contributions(
        self,
        contributions,
        skip_dupe_check=False,
        ignore_dupes=False,
        retry=False,
        per_page=100,
        max_workers=3,
    ):
        """Convenience function to submit a list of contributions

        Args:
            contributions (list): list of contribution dicts to submit
            skip_dupe_check (bool): skip check for duplicates of identifiers and components
            ignore_dupes (bool): force duplicate components to be submitted
            retry (bool): keep trying until all contributions successfully submitted
            per_page (int): number of contributions to submit in each chunk/request
            max_workers (int): number of parallel requests to use to submit chunk
        """
        tic = time.perf_counter()

        if max_workers > MAX_WORKERS:
            max_workers = MAX_WORKERS
            print(f"max_workers reset to max {MAX_WORKERS}")

        # get existing contributions
        print("get existing contributions ...")
        existing = defaultdict(set)
        existing["unique_identifiers"] = True
        project_name = contributions[0]["project"]

        if not skip_dupe_check:
            existing = self.get_contributions(project_name)

        # prepare contributions
        print("prepare contributions ...")
        contribs = []
        digests = defaultdict(set)
        components = {"structures", "tables"}
        fields = [
            comp
            for comp in self.swagger_spec.definitions.get(
                "ContributionsSchema"
            )._properties.keys()
            if comp not in components
        ]

        # TODO parallelize?
        for contrib in tqdm(contributions, leave=False):
            if (
                existing["unique_identifiers"]
                and contrib["identifier"] in existing["identifiers"]
            ):
                continue

            contribs.append({k: deepcopy(contrib[k]) for k in fields if k in contrib})

            for component in components:
                contribs[-1][component] = []
                elements = contrib.get(component, [])
                nelems = len(elements)

                for idx, element in enumerate(elements):
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
                        element.index = element.index.astype(str)
                        for col in element.columns:
                            element[col] = element[col].astype(str)
                        dct = element.to_dict(orient="split")

                    digest = get_md5(dct)

                    if is_structure:
                        dct["name"] = getattr(element, "name", None)
                        if not dct["name"]:
                            c = element.composition
                            comp = c.get_integer_formula_and_factor()
                            dct["name"] = f"{comp[0]}-{idx}" if nelems > 1 else comp[0]
                    else:
                        name = f"table-{idx}" if nelems > 1 else "table"
                        dct["name"] = element.attrs.get("name", name)
                        title = element.attrs.get("title", dct["name"])
                        labels = element.attrs.get("labels", {})
                        index = element.index.name
                        variable = element.columns.name

                        if index and "index" not in labels:
                            labels["index"] = index
                        if variable and "variable" not in labels:
                            labels["variable"] = variable

                        dct["attrs"] = {"title": title, "labels": labels}

                    dupe = digest in digests[component] or digest in existing[component]

                    if not ignore_dupes and dupe:
                        msg = f"Duplicate: {dct['name']}!"
                        raise ValueError(msg)

                    if not dupe:
                        digests[component].add(digest)
                        contribs[-1][component].append(dct)

        # submit contributions
        if contribs:
            print("submit contributions ...")
            with FuturesSession(max_workers=max_workers) as session:
                # bravado future doesn't work with concurrent.futures
                ncontribs = len(contribs)
                headers = {"Content-Type": "application/json"}
                headers.update(self.headers)

                @sleep_and_retry
                @limits(calls=175, period=60)
                def post_future(chunk):
                    return session.post(
                        f"{self.url}/contributions/",
                        headers=headers,
                        data=json.dumps(chunk).encode("utf-8"),
                    )

                while contribs:
                    futures = [
                        post_future(chunk) for chunk in chunks(contribs, n=per_page)
                    ]

                    self._run_futures(futures, total=len(contribs))

                    if existing["unique_identifiers"] and retry:
                        existing = self.get_contributions(project_name)
                        contribs = [
                            c
                            for c in contribs
                            if c["identifier"] not in existing["identifiers"]
                        ]
                    else:
                        contribs = []  # abort retrying
                        if not existing["unique_identifiers"] and retry:
                            print("Please resubmit failed contributions manually.")

                self.load()
                toc = time.perf_counter()
                dt = (toc - tic) / 60
                print(f"It took {dt:.1f}min to submit {ncontribs} contributions.")
        else:
            print("Nothing to submit.")

    def _run_futures(self, futures, total=None):
        """helper to run futures/requests"""
        responses = {}

        with tqdm(leave=False, total=total if total else len(futures)) as pbar:
            for future in as_completed(futures):
                response = future.result()
                status = response.status_code

                if status in {200, 201, 400, 401, 404, 500, 502}:
                    resp = response.json()
                    if status in {200, 201}:
                        if total:
                            cnt = len(resp["data"]) if "data" in resp else resp["count"]
                        else:
                            cnt = 1
                        pbar.update(cnt)
                        if hasattr(future, "track_id"):
                            responses[future.track_id] = resp
                        if "warning" in resp:
                            print(resp["warning"])
                    elif status != 502:
                        warnings.warn(resp["error"])
                elif status not in {503, 504}:
                    warnings.warn(response.content.decode("utf-8"))

        return responses
