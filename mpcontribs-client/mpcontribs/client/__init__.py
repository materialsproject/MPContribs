# -*- coding: utf-8 -*-
import sys
import os
import json
import fido
import time
import gzip
import warnings
import pandas as pd
import plotly.io as pio
import itertools

from bravado_core.param import Param
from bson.objectid import ObjectId
from typing import Union, Type, List
from tqdm.auto import tqdm
from hashlib import md5
from pathlib import Path
from copy import deepcopy
from filetype import guess
from flatten_dict import flatten, unflatten
from base64 import b64encode, b64decode
from urllib.parse import urlparse
from pyisemail import is_email
from collections import defaultdict
from pyisemail.diagnosis import BaseDiagnosis
from swagger_spec_validator.common import SwaggerValidationError
from jsonschema.exceptions import ValidationError
from bravado_core.formatter import SwaggerFormat
from bravado.client import SwaggerClient
from bravado.fido_client import FidoClient  # async
from bravado.http_future import HttpFuture
from bravado.swagger_model import Loader
from bravado.config import bravado_config_from_config_dict
from bravado_core.spec import Spec
from bravado.exception import HTTPNotFound
from bravado_core.validate import validate_object
from json2html import Json2Html
from IPython.display import display, HTML, Image, FileLink
from boltons.iterutils import remap
from pymatgen.core import Structure as PmgStructure
from concurrent.futures import as_completed
from requests_futures.sessions import FuturesSession
from urllib3.util.retry import Retry
from filetype.types.archive import Gz
from filetype.types.image import Jpeg, Png, Gif, Tiff
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from datetime import datetime

RETRIES = 3
MAX_WORKERS = 10
MAX_ELEMS = 10
MAX_BYTES = 1200 * 1024
DEFAULT_HOST = "contribs-api.materialsproject.org"
BULMA = "is-narrow is-fullwidth has-background-light"
PROVIDERS = {"github", "google", "facebook", "microsoft", "amazon"}
COMPONENTS = ["structures", "tables", "attachments"]  # using list to maintain order
SUBDOMAINS = ["contribs", "lightsources", "ml", "workshop-contribs"]
LOCAL_STACK = {
    "contribs-api": 5000, "workshop-contribs-api": 5005,
    "contribs-ml-api": 5002, "contribs-lightsources-api": 5003,
}
VALID_URLS = {f"http://localhost:{p}" for p in LOCAL_STACK.values()}  # AWS Fargate Task
VALID_URLS |= {f"http://{h}:{p}" for h, p in LOCAL_STACK.items()}  # local docker-compose stack
VALID_URLS |= {f"https://{n}-api.materialsproject.org" for n in SUBDOMAINS}
VALID_URLS |= {f"http://localhost.{n}-api.materialsproject.org" for n in SUBDOMAINS}
SUPPORTED_FILETYPES = (Gz, Jpeg, Png, Gif, Tiff)
SUPPORTED_MIMES = [t().mime for t in SUPPORTED_FILETYPES]
DEFAULT_DOWNLOAD_DIR = Path.home() / "mpcontribs-downloads"

j2h = Json2Html()
pd.options.plotting.backend = "plotly"
pd.set_option('mode.use_inf_as_na', True)
pio.templates.default = "simple_white"
warnings.formatwarning = lambda msg, *args, **kwargs: f"{msg}\n"
warnings.filterwarnings("default", category=DeprecationWarning, module=__name__)

ureg = UnitRegistry(
    autoconvert_offset_to_baseunit=True,
    preprocessors=[
        lambda s: s.replace("%%", " permille "),
        lambda s: s.replace("%", " percent "),
    ],
)
ureg.define(UnitDefinition("percent", "%", (), ScaleConverter(0.01)))
ureg.define(UnitDefinition("permille", "%%", (), ScaleConverter(0.001)))
ureg.define(UnitDefinition("ppm", "ppm", (), ScaleConverter(1e-6)))
ureg.define(UnitDefinition("ppb", "ppb", (), ScaleConverter(1e-9)))
ureg.define("atom = 1")
ureg.define("bohr_magneton = e * hbar / (2 * m_e) = µᵇ = µ_B = mu_B")
ureg.define("electron_mass = 9.1093837015e-31 kg = mₑ = m_e")


def get_md5(d):
    s = json.dumps(d, sort_keys=True).encode("utf-8")
    return md5(s).hexdigest()


def validate_email(email_string):
    if email_string.count(":") != 1:
        raise SwaggerValidationError(f"{email_string} not of format <provider>:<email>.")

    provider, email = email_string.split(":", 1)
    if provider not in PROVIDERS:
        raise SwaggerValidationError(f"{provider} is not a valid provider.")

    d = is_email(email, diagnose=True)
    if d > BaseDiagnosis.CATEGORIES["VALID"]:
        raise SwaggerValidationError(f"{email} {d.message}")


email_format = SwaggerFormat(
    format="email",
    to_wire=str,
    to_python=str,
    validate=validate_email,
    description="e-mail address including provider",
)


def validate_url(url_string, qualifying=("scheme", "netloc")):
    tokens = urlparse(url_string)
    if not all([getattr(tokens, qual_attr) for qual_attr in qualifying]):
        raise SwaggerValidationError(f"{url_string} invalid")


url_format = SwaggerFormat(
    format="url", to_wire=str, to_python=str, validate=validate_url, description="URL",
)


# https://stackoverflow.com/a/8991553
def grouper(n, iterable):
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk


def get_session():
    adapter_kwargs = dict(max_retries=Retry(
        total=RETRIES,
        read=RETRIES,
        connect=RETRIES,
        respect_retry_after_header=True,
        status_forcelist=[429],  # rate limit
    ))
    s = FuturesSession(max_workers=MAX_WORKERS, adapter_kwargs=adapter_kwargs)
    s.hooks['response'].append(_response_hook)
    return s


def _response_hook(resp, *args, **kwargs):
    content_type = resp.headers['content-type']
    if content_type == "application/json":
        result = resp.json()

        if "data" in result and isinstance(result["data"], list):
            resp.result = result
            resp.count = len(result["data"])
        elif "count" in result and isinstance(result["count"], int):
            resp.count = result["count"]

        if "warning" in result:
            print("WARNING", result["warning"])
        elif "error" in result and isinstance(result["error"], str):
            print("ERROR", result["error"][:10000] + "...")

    elif content_type == "application/gzip":
        resp.result = resp.content
    else:
        print("ERROR", resp.content.decode("utf-8"))


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


def _in_ipython():
    ipython = sys.modules['IPython'].get_ipython()
    return ipython is not None and 'IPKernelApp' in ipython.config


class Dict(dict):
    """Custom dictionary to display itself as HTML table with Bulma CSS"""
    def display(self, attrs: str = f'class="table {BULMA}"'):
        """Nice table display of dictionary

        Args:
            attrs (str): table attributes to forward to Json2Html.convert
        """
        html = j2h.convert(json=remap(self, visit=visit), table_attributes=attrs)
        if _in_ipython():
            return display(HTML(html))

        return html


class Table(pd.DataFrame):
    """Wrapper class around pandas.DataFrame to provide display() and info()"""
    def display(self):
        """Display a plotly graph for the table if in IPython/Jupyter"""
        if _in_ipython():
            try:
                return self.plot(**self.attrs)
            except Exception as e:
                print(f"Can't display table: {e}")

        return self

    def info(self) -> Type[Dict]:
        """Show summary info for table"""
        info = Dict((k, v) for k, v in self.attrs.items())
        info["columns"] = ", ".join(self.columns)
        info["nrows"] = len(self.index)
        return info


class Structure(PmgStructure):
    """Wrapper class around pymatgen.Structure to provide display() and info()"""
    def display(self):
        return self  # TODO use static image from crystal toolkit?

    def info(self) -> Type[Dict]:
        """Show summary info for structure"""
        info = Dict((k, v) for k, v in self.attrs.items())
        info["formula"] = self.composition.formula
        info["reduced_formula"] = self.composition.reduced_formula
        info["nsites"] = len(self)
        return info


class Attachment(dict):
    """Wrapper class around dict to handle attachments"""
    def decode(self) -> str:
        """Decode base64-encoded content of attachment"""
        return b64decode(self["content"], validate=True)

    def write(self, outdir: Union[str, Path] = None) -> Path:
        """Write attachment to file using its name

        Args:
            outdir (str,Path): existing directory to which to write file
        """
        outdir = outdir or "."
        path = Path(outdir) / self.name
        content = self.decode()
        path.write_bytes(content)
        return path

    def display(self, outdir: Union[str, Path] = None):
        """Display Image/FileLink for attachment if in IPython/Jupyter

        Args:
            outdir (str,Path): existing directory to which to write file
        """
        if _in_ipython():
            if self["mime"].startswith("image/"):
                content = self.decode()
                return Image(content)

            self.write(outdir=outdir)
            return FileLink(self.name)

        return self.info().display()

    def info(self) -> Dict:
        """Show summary info for attachment"""
        fields = ["id", "name", "mime", "md5"]
        info = Dict((k, v) for k, v in self.items() if k in fields)
        info["size"] = len(self.decode())
        return info

    @property
    def name(self) -> str:
        """name of the attachment (used in filename)"""
        return self["name"]

    @classmethod
    def from_data(cls, name: str, data: Union[list, dict]):
        """Construct attachment from data dict or list

        Args:
            name (str): name for the attachment
            data (list,dict): JSON-serializable data to go into the attachment
        """
        filename = name + ".json.gz"
        data_json = json.dumps(data, indent=4).encode("utf-8")
        content = gzip.compress(data_json)
        size = len(content)

        if size > MAX_BYTES:
            raise ValueError(f"{name} too large ({size} > {MAX_BYTES})!")

        return cls(
            name=filename,
            mime="application/gzip",
            content=b64encode(content).decode("utf-8")
        )


def load_client(apikey=None, headers=None, host=None):
    warnings.warn(
        "load_client(...) is deprecated, use Client(...) instead", DeprecationWarning
    )


def _run_futures(futures, total: int = 0, timeout: int = -1):
    """helper to run futures/requests"""
    start = time.perf_counter()
    total_set = total > 0
    total = total if total_set else len(futures)
    responses = {}

    with tqdm(leave=False, total=total) as pbar:
        for future in as_completed(futures):
            if not future.cancelled():
                response = future.result()
                cnt = response.count if total_set and hasattr(response, "count") else 1
                pbar.update(cnt)

                if hasattr(future, "track_id") and hasattr(response, "result"):
                    responses[future.track_id] = response.result

                elapsed = time.perf_counter() - start
                timed_out = timeout > 0 and elapsed > timeout

                if timed_out or not response.ok:
                    for future in futures:
                        future.cancel()

    return responses


class Client(SwaggerClient):
    """client to connect to MPContribs API

    Typical usage:
        - set environment variable MPCONTRIBS_API_KEY to the API key from your MP profile
        - import and init:
          >>> from mpcontribs.client import Client
          >>> client = Client()
    """
    # We only want to load the swagger spec from the remote server when needed and not
    # everytime the client is initialized. Hence using the Borg design nonpattern (instead
    # of Singleton): Since the __dict__ of any instance can be re-bound, Borg rebinds it
    # in its __init__ to a class-attribute dictionary. Now, any reference or binding of an
    # instance attribute will actually affect all instances equally.
    # NOTE bravado future doesn't work with concurrent.futures

    _shared_state = {}

    def __init__(self, apikey: str = None, headers: dict = None, host: str = None):
        """Initialize the client - only reloads API spec from server as needed

        Args:
            apikey (str): API key (or use MPCONTRIBS_API_KEY env var) - ignored if headers set
            headers (dict): custom headers for localhost connections
            host (str): host address to connect to (or use MPCONTRIBS_API_HOST env var)
        """
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
        self.headers = headers or {}
        self.headers = {"x-api-key": apikey} if apikey else self.headers
        self.headers["Content-Type"] = "application/json"
        self.host = host
        ssl = host.endswith(".materialsproject.org") and not host.startswith("localhost.")
        self.protocol = "https" if ssl else "http"
        self.url = f"{self.protocol}://{self.host}"
        self.session = get_session()

        if self.url not in VALID_URLS:
            raise ValueError(f"{self.url} not a valid URL (one of {VALID_URLS})")

        if "swagger_spec" not in self.__dict__ or (
            self.swagger_spec.http_client.headers != self.headers
        ) or (
            self.swagger_spec.spec_dict["host"] != self.host
        ):
            self._load()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.session.close()

    def _load(self):
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

        columns = {"string": [], "number": []}

        for project in resp["data"]:
            for column in project["columns"]:
                if column["path"].startswith("data."):
                    col = column["path"].replace(".", "__")
                    if column["unit"] == "NaN":
                        columns["string"].append(col)
                    else:
                        col = f"{col}__value"
                        columns["number"].append(col)

        resource = self.swagger_spec.resources["contributions"]

        for operation_id, operation in resource.operations.items():
            for pn in list(operation.params.keys()):
                if pn.startswith("data_"):
                    param = operation.params.pop(pn)
                    op = param.name.rsplit('$__', 1)[-1]
                    typ = param.param_spec.get("type")
                    key = "number" if typ == "number" else "string"

                    for column in columns[key]:
                        param_name = f"{column}__{op}"
                        param_spec = deepcopy(param.param_spec)
                        param_spec["name"] = param_name
                        param_spec.pop("description")
                        operation.params[param_name] = Param(
                            self.swagger_spec, operation, param_spec
                        )

    def __dir__(self):
        members = set(self.swagger_spec.resources.keys())
        members |= set(k for k in self.__dict__.keys() if not k.startswith("_"))
        members |= set(k for k in dir(self.__class__) if not k.startswith("_"))
        return members

    def _is_valid_payload(self, model: str, data: dict):
        model_spec = deepcopy(self.get_model(f"{model}sSchema")._model_spec)
        model_spec.pop("required")
        model_spec['additionalProperties'] = False

        try:
            validate_object(self.swagger_spec, model_spec, data)
        except ValidationError as ex:
            return str(ex)

        return True

    def _get_per_page_default_max(self, op: str = "get", resource: str = "contributions") -> int:
        resource = self.swagger_spec.resources[resource]
        param_spec = getattr(resource, f"{op}_entries").params["per_page"].param_spec
        return param_spec["default"], param_spec["maximum"]

    def _get_per_page(
        self, per_page: int, op: str = "get", resource: str = "contributions"
    ) -> int:
        _, per_page_max = self._get_per_page_default_max(op=op, resource=resource)
        return min(per_page_max, per_page)

    def _split_query(
        self,
        query: dict,
        op: str = "get",
        resource: str = "contributions",
        pages: int = -1,
    ) -> List[dict]:
        """Avoid URI too long errors"""
        pp_default, pp_max = self._get_per_page_default_max(op=op, resource=resource)
        per_page = pp_default if "id__in" in query else pp_max
        query["per_page"] = per_page
        nr_params_to_split = sum(
            len(v) > per_page for v in query.values() if isinstance(v, list)
        )
        if nr_params_to_split > 1:
            raise NotImplementedError(
                f"More than one list in query with length > {per_page} not supported!"
            )

        queries = []

        for k, v in query.items():
            if isinstance(v, list) and len(v) > per_page:
                for chunk in grouper(per_page, v):
                    queries.append({k: list(chunk)})

        if not queries:
            queries = [query]

        if len(queries) == 1 and pages and pages > 0:
            queries = []
            for page in range(1, pages+1):
                queries.append(deepcopy(query))
                queries[-1]["page"] = page

        for q in queries:
            # copy over missing parameters
            for k, v in query.items():
                if k not in q:
                    q[k] = v

            # comma-separated lists
            for k, v in q.items():
                if isinstance(v, list):
                    q[k] = ",".join(v)

        return queries

    def _get_future(
        self,
        track_id,
        params: dict,
        rel_url: str = "contributions",
        op: str = "get"
    ):
        if self.session and self.session.executor._shutdown:
            raise ValueError("Session closed. Use `with` statement.")

        future = getattr(self.session, op)(
            f"{self.url}/{rel_url}/", headers=self.headers, params=params
        )
        setattr(future, "track_id", track_id)
        return future

    def get_project_names(self) -> List[str]:
        """Retrieve list of project names."""
        resp = self.projects.get_entries(_fields=["name"]).result()
        return [p["name"] for p in resp["data"]]

    def get_project(self, name: str) -> Type[Dict]:
        """Retrieve full project entry

        Args:
            name (str): name of the project
        """
        return Dict(self.projects.get_entry(pk=name, _fields=["_all"]).result())

    def get_contribution(self, cid: str) -> Type[Dict]:
        """Retrieve full contribution entry

        Args:
            cid (str): contribution ObjectID
        """
        fields = list(self.get_model("ContributionsSchema")._properties.keys())
        fields.remove("needs_build")  # internal field
        return Dict(self.contributions.get_entry(pk=cid, _fields=fields).result())

    def get_table(self, tid_or_md5: str) -> Type[Table]:
        """Retrieve full Pandas DataFrame for a table

        Args:
            tid_or_md5 (str): ObjectId or MD5 hash digest for table
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

        op = self.swagger_spec.resources["tables"].get_entries
        per_page = op.params["data_per_page"].param_spec["maximum"]
        table = {"data": []}
        page, pages = 1, None

        while pages is None or page <= pages:
            resp = self.tables.get_entry(
                pk=tid, _fields=["_all"], data_page=page, data_per_page=per_page
            ).result()
            table["data"].extend(resp["data"])
            if pages is None:
                pages = resp["total_data_pages"]
                table["index"] = resp["index"]
                table["columns"] = resp["columns"]
                table["attrs"] = resp.get("attrs", {})
                for field in ["id", "name", "md5"]:
                    table["attrs"][field] = resp[field]

            page += 1

        df = pd.DataFrame.from_records(
            table["data"], columns=table["columns"], index=table["index"]
        ).apply(pd.to_numeric, errors="ignore")
        df.index = pd.to_numeric(df.index, errors="ignore")
        labels = table["attrs"].get("labels", {})

        if "index" in labels:
            df.index.name = labels["index"]
        if "variable" in labels:
            df.columns.name = labels["variable"]

        ret = Table(df)
        attrs_keys = self.get_model("TablesSchema")._properties["attrs"]["properties"].keys()
        ret.attrs = {k: v for k, v in table["attrs"].items() if k in attrs_keys}
        return ret

    def get_structure(self, sid_or_md5: str) -> Type[Structure]:
        """Retrieve pymatgen structure

        Args:
            sid_or_md5 (str): ObjectId or MD5 hash digest for structure
        """
        str_len = len(sid_or_md5)
        if str_len not in {24, 32}:
            raise ValueError(f"'{sid_or_md5}' is not a valid structure id or md5 hash digest!")

        if str_len == 32:
            structures = self.structures.get_entries(md5=sid_or_md5, _fields=["id"]).result()
            if not structures:
                raise ValueError(f"structure for md5 '{sid_or_md5}' not found!")
            sid = structures["data"][0]["id"]
        else:
            sid = sid_or_md5

        fields = list(self.get_model("StructuresSchema")._properties.keys())
        resp = self.structures.get_entry(pk=sid, _fields=fields).result()
        ret = Structure.from_dict(resp)
        ret.attrs = {
            field: resp[field]
            for field in ["id", "name", "md5"]
        }
        return ret

    def get_attachment(self, aid_or_md5: str) -> Type[Attachment]:
        """Retrieve an attachment

        Args:
            aid_or_md5 (str): ObjectId or MD5 hash digest for attachment
        """
        str_len = len(aid_or_md5)
        if str_len not in {24, 32}:
            raise ValueError(f"'{aid_or_md5}' is not a valid attachment id or md5 hash digest!")

        if str_len == 32:
            attachments = self.attachments.get_entries(
                md5=aid_or_md5, _fields=["id"]
            ).result()
            if not attachments:
                raise ValueError(f"attachment for md5 '{aid_or_md5}' not found!")
            aid = attachments["data"][0]["id"]
        else:
            aid = aid_or_md5

        return Attachment(self.attachments.get_entry(pk=aid, _fields=["_all"]).result())

    def init_columns(self, name: str, columns: dict) -> dict:
        """initialize columns for a project to set their order and desired units

        The `columns` field tracks the minima and maxima of each `data` field as
        contributions are submitted. This function should thus be executed before
        submitting contributions, or all contributions for a project should be deleted to
        ensure clean initialization of all columns. If columns are not initialized using
        this function, `submit_contributions` will respect the order of columns as they
        are submitted and will auto-determine suitable units based on the first
        contribution containing a respective data column. `init_columns` can be used at
        any point to reset the order of columns, though. Previously determined `min/max`
        values for the affected data fields will be respected.

        The `columns` argument is a dictionary which maps the data field names to its
        units. Use `None` to indicate that a field is not a quantity (plain string). The
        unit for a dimensionless quantity is an empty string (""). Percent (`%`) and
        permille (`%%`) are considered units. Nested fields are indicated using a dot
        (".") in the data field name.

        Example:

        >>> client.init_columns("sandbox", {"a": None, "b.c": "eV", "b.d": "mm", "e": ""})

        This example will result in column headers on the project landing page of the form


        |      |      data       |      |
        | data |        b        | data |
        |   a  | c [eV] | d [mm] | e [] |


        Args:
            name (str): name of the project for which to initialize data columns
            columns (dict): dictionary mapping data column to its unit
        """
        if not isinstance(name, str):
            return {"error": "`name` argument must be a string!"}

        if not isinstance(columns, dict):
            return {"error": "`columns` argument must be a dict!"}

        existing_columns = set()
        for k, v in columns.items():
            if k in COMPONENTS:
                existing_columns.add(k)
                continue

            nesting = k.count(".")
            if nesting > 4:
                return {"error": f"Nesting too deep for {k}"}

            for col in existing_columns:
                if nesting and col.startswith(k):
                    return {"error": f"duplicate definition of {k} in {col}!"}

                for n in range(1, nesting+1):
                    if k.rsplit(".", n)[0] == col:
                        return {"error": f"Ancestor of {k} already defined in {col}!"}

            is_valid_string = isinstance(v, str) and v.lower() != "nan"
            if not is_valid_string and v is not None:
                return {"error": f"Unit '{v}' for {k} invalid (use `None` or a non-NaN string)!"}

            if v != "" and v is not None and v not in ureg:
                return {"error": f"Unit '{v}' for {k} invalid!"}

            existing_columns.add(k)

        valid_projects = self.get_project_names()

        if name not in valid_projects:
            return {"error": f"{name} doesn't exist or you don't have access!"}

        # sort to avoid "overlapping columns" error in handsontable's NestedHeaders
        sorted_columns = flatten(unflatten(columns, splitter="dot"), reducer="dot")

        # reconcile with existing columns
        resp = self.projects.get_entry(pk=name, _fields=["columns"]).result()
        existing_columns, new_columns = {}, []

        for col in resp["columns"]:
            path = col.pop("path")
            existing_columns[path] = col

        for path, unit in sorted_columns.items():
            if path in COMPONENTS:
                new_columns.append({"path": path})
                continue

            full_path = f"data.{path}"
            new_column = {"path": full_path}
            existing_column = existing_columns.get(full_path)

            if unit is not None:
                new_column["unit"] = unit

            if existing_column:
                for k in ["min", "max"]:
                    v = existing_column.get(k)
                    if v:
                        new_column[k] = v

                # NOTE if existing_unit == "NaN":
                #   it was set by omitting "unit" in new_column
                new_unit = new_column.get("unit", "NaN")
                existing_unit = existing_column.get("unit")
                if existing_unit != new_unit:
                    try:
                        ureg.Quantity(existing_unit).to(new_unit)
                    except DimensionalityError:
                        return {
                            "error": f"Can't convert {existing_unit} to {new_unit} for {path}"
                        }

                    # TODO scale contributions to new unit
                    return {"error": "Changing units not supported yet. Please resubmit"
                            " contributions or update accordingly."}

            new_columns.append(new_column)

        payload = {"columns": new_columns}
        valid = self._is_valid_payload("Project", payload)
        if not valid:
            return {"error": valid}

        self.projects.update_entry(pk=name, project={"columns": []}).result()
        return self.projects.update_entry(pk=name, project=payload).result()

    def delete_contributions(self, name: str):
        """Remove all contributions for a project

        Note: This also resets the columns field for a project. It might have to be
        re-initialized via `client.init_columns()`.

        Args:
            name (str): name of the project for which to delete contributions
        """
        tic = time.perf_counter()
        # reset columns to be save (sometimes not all are reset BUGFIX?)
        self.projects.update_entry(pk=name, project={"columns": []}).result()
        cids = list(self.get_all_ids(dict(project=name)).get(name, {}).get("ids", set()))

        if not cids:
            print(f"There aren't any contributions to delete for {name}")
            return

        total = len(cids)
        query = {"id__in": cids}
        _, total_pages = self.get_totals(query=query)
        queries = self._split_query(query, op="delete", pages=total_pages)
        futures = [self._get_future(i, q, op="delete") for i, q in enumerate(queries)]
        _run_futures(futures, total=total)
        left, _ = self.get_totals(query=dict(project=name))
        deleted = total - left
        self._load()
        toc = time.perf_counter()
        dt = (toc - tic) / 60
        print(f"It took {dt:.1f}min to delete {deleted} contributions.")

        if left:
            print(f"There were errors and {left} contributions are left to delete!")

    def get_totals(
        self,
        query: dict = None,
        timeout: int = -1,
        resource: str = "contributions",
        op: str = "get"
    ) -> tuple:
        """Retrieve total count and pages for resource entries matching query

        Args:
            query (dict): query to select resource entries
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
            op (str): operation to calculate total pages for, one of
                      ("get", "create", "update", "delete", "download")

        Returns:
            tuple of total counts and pages
        """
        ops = {"get", "create", "update", "delete", "download"}
        if op not in ops:
            print(f"`op` has to be one of {ops}")
            return

        query = query or {}
        skip_keys = {"per_page", "_fields", "format"}
        query = {k: v for k, v in query.items() if k not in skip_keys}
        query["_fields"] = ["_id"]
        queries = self._split_query(query, resource=resource, op=op)  # don't paginate
        result = {"total_count": 0, "total_pages": 0}
        futures = [self._get_future(i, q, rel_url=resource) for i, q in enumerate(queries)]
        responses = _run_futures(futures, timeout=timeout)

        for resp in responses.values():
            for k in result:
                result[k] += resp[k]

        return result["total_count"], result["total_pages"]

    def get_unique_identifiers_flags(self, projects: list = None) -> dict:
        """Retrieve values for `unique_identifiers` flags for a list of projects

        Args:
            projects (list): list of project names - return all if not set

        Returns:
            {"<project-name>": True|False, ...}
        """
        unique_identifiers = {}
        query = {"name__in": projects} if projects else {}
        resp = self.projects.get_entries(
            _fields=["name", "unique_identifiers"], **query
        ).result()

        for project in resp["data"]:
            project_name = project["name"]
            unique_identifiers[project_name] = project["unique_identifiers"]

        return unique_identifiers

    def get_all_ids(
        self,
        query: dict,
        include: List[str] = None,
        timeout: int = -1,
        data_id_fields: dict = None,
        fmt: str = "sets",
        op: str = "get",
    ) -> dict:
        """Retrieve a list of existing contribution and component (Object)IDs

        Args:
            query (dict): query to select contributions
            include (list): components to include in response
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
            data_id_fields (dict): map of project to extra field in `data` to include as ID field
            fmt (str): return `sets` of identifiers or `map` (see below)
            op (str): operation to calculate total pages for, one of
                      ("get", "create", "update", "delete", "download")

        Returns:
            {"<project-name>": {
                # if fmt == "sets":
                "ids": {<set of contributions IDs>},
                "identifiers": {<set of contribution identifiers>},
                "<data_id_field>_set": {<set of data_id_field values>},
                "structures|tables|attachments": {
                    "ids": {<set of structure|table|attachment IDs>},
                    "md5s": {<set of structure|table|attachment md5s>}
                },
                # if fmt == "map" and unique_identifiers=True
                "<identifier>": {
                    "id": "<contribution ID>",
                    "<data_id_field>": "<data_id_field value>",
                    "structures|tables|attachments": {
                        "<name>": {
                            "id": "<structure|table|attachment ID>",
                            "md5": "<structure|table|attachment md5>"
                        }, ...
                    }
                }
                # if fmt == "map" and unique_identifiers=False (data_id_field required)
                "<identifier>": {
                    "<data_id_field value>": {
                        "id": "<contribution ID>",
                        "structures|tables|attachments": {
                            "<name>": {
                                "id": "<structure|table|attachment ID>",
                                "md5": "<structure|table|attachment md5>"
                            }, ...
                        }
                    }, ...
                }
            }, ...}
        """
        include = include or []
        components = set(x for x in include if x in COMPONENTS)
        if include and not components:
            print(f"`include` must be subset of {COMPONENTS}!")
            return

        fmts = {"sets", "map"}
        if fmt not in fmts:
            print(f"`fmt` must be subset of {fmts}!")
            return

        ops = {"get", "create", "update", "delete", "download"}
        if op not in ops:
            print(f"`op` has to be one of {ops}")
            return

        unique_identifiers = self.get_unique_identifiers_flags()
        data_id_fields = {
            k: v for k, v in data_id_fields.items()
            if k in unique_identifiers and isinstance(v, str)
        } if data_id_fields else {}

        ret = {}
        query = query or {}
        [query.pop(k, None) for k in ["page", "per_page", "_fields"]]
        id_fields = {"project", "id", "identifier"}

        if data_id_fields:
            id_fields.update(
                f"data.{data_id_field}"
                for data_id_field in data_id_fields.values()
            )

        query["_fields"] = list(id_fields | components)
        _, total_pages = self.get_totals(query=query, timeout=timeout)
        queries = self._split_query(query, op=op, pages=total_pages)
        futures = [self._get_future(i, q) for i, q in enumerate(queries)]
        responses = _run_futures(futures, timeout=timeout)

        for resp in responses.values():
            for contrib in resp["data"]:
                project = contrib["project"]
                data_id_field = data_id_fields.get(project)

                if fmt == "sets":
                    if project not in ret:
                        id_keys = ["ids", "identifiers"]
                        if data_id_field:
                            id_field = f"{data_id_field}_set"
                            id_keys.append(id_field)

                        ret[project] = {k: set() for k in id_keys}

                    ret[project]["ids"].add(contrib["id"])
                    ret[project]["identifiers"].add(contrib["identifier"])

                    if data_id_field:
                        ret[project][id_field].add(contrib["data"][data_id_field])

                    for component in components:
                        if component in contrib:
                            if component not in ret[project]:
                                ret[project][component] = {"ids": set(), "md5s": set()}

                            for d in contrib[component]:
                                for k in ["id", "md5"]:
                                    ret[project][component][f"{k}s"].add(d[k])

                elif fmt == "map":
                    identifier = contrib["identifier"]
                    data_id_field_val = contrib.get("data", {}).get(data_id_field)

                    if project not in ret:
                        ret[project] = {}

                    if unique_identifiers[project]:
                        ret[project][identifier] = {"id": contrib["id"]}

                        if data_id_field and data_id_field_val:
                            ret[project][identifier][data_id_field] = data_id_field_val

                        for component in components:
                            if component in contrib:
                                ret[project][identifier][component] = {
                                    d["name"]: {"id": d["id"], "md5": d["md5"]}
                                    for d in contrib[component]
                                }

                    elif data_id_field and data_id_field_val:
                        ret[project][identifier] = {
                            data_id_field_val: {"id": contrib["id"]}
                        }

                        for component in components:
                            if component in contrib:
                                ret[project][identifier][data_id_field_val][component] = {
                                    d["name"]: {"id": d["id"], "md5": d["md5"]}
                                    for d in contrib[component]
                                }

        return ret

    def update_contributions(self, name: str, data: dict, query: dict = None) -> dict:
        """Apply the same update to all contributions in a project (matching query)

        See `client.contributions.get_entries()` for keyword arguments used in query.
        NOTE: Still needs to be parallelized - could be slow.

        Args:
            name (str): name of the project
            data (dict): update to apply on every matching contribution
            query (dict): optional query to select contributions
        """
        if not data:
            return "Nothing to update."

        valid = self._is_valid_payload("Contribution", data)
        if not valid:
            return {"error": valid}

        _, per_page = self._get_per_page_default_max(op="update")
        query = query or {}
        query["project"] = name
        has_more = True
        updated = 0

        while has_more:
            resp = self.contributions.update_entries(
                contributions=data, per_page=per_page, **query
            ).result()
            has_more = resp["has_more"]
            updated += resp["count"]

        print(f"Updated {updated} contributions.")

    def publish(self, name: str, recursive: bool = False) -> dict:
        """Publish a project and optionally its contributions

        NOTE: Still needs to be parallelized - recursive update slow and incomplete.

        Args:
            name (str): name of the project
            recursive (bool): also publish according contributions?
        """
        try:
            resp = self.projects.get_entry(pk=name, _fields=["is_public"]).result()
        except HTTPNotFound:
            return {"error": f"project `{name}` not found or access denied!"}

        is_public = resp["is_public"]

        if not recursive and is_public:
            return {"warning": f"project `{name}` already public (recursive=False)."}

        if not is_public:
            self.projects.update_entry(pk=name, project={"is_public": True}).result()

        if recursive:
            self.update_contributions(name, {"is_public": True}, {"is_public": False})

    def submit_contributions(
        self,
        contributions: List[dict],
        ignore_dupes: bool = False,
        retry: bool = False,
        per_request: int = 100,
        timeout: int = -1
    ):
        """Submit a list of contributions

        Example for a single contribution dictionary:

        {
            "project": "sandbox",
            "identifier": "mp-4",
            "data": {
                "a": "3 eV",
                "b": {"c": "hello", "d": 3},
                "d.e.f": "nest via dot-notation"
            },
            "structures": [<pymatgen Structure>, ...],
            "tables": [<pandas DataFrame>, ...],
            "attachments": [<pathlib.Path>, <mpcontribs.client.Attachment>, ...]
        }

        This function can also be used to update contributions by including the respective
        contribution `id`s in the above dictionary and only including fields that need
        updating. Set list entries to `None` for components that are to be left untouched
        during an update.

        Args:
            contributions (list): list of contribution dicts to submit
            ignore_dupes (bool): force duplicate components to be submitted
            retry (bool): keep trying until all contributions successfully submitted
            per_request (int): number of contributions to submit per request
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        if not contributions or not isinstance(contributions, list):
            print("Please provide list of contributions to submit.")
            return

        # get existing contributions
        tic = time.perf_counter()
        project_names = set()
        collect_ids = []
        require_one_of = {"data"} | set(COMPONENTS)
        per_page = self._get_per_page(per_request)

        for idx, c in enumerate(contributions):
            has_keys = require_one_of & c.keys()
            if not has_keys:
                return {"error": f"Nothing to submit for contribution #{idx}!"}
            elif not all(c[k] for k in has_keys):
                for k in has_keys:
                    if not c[k]:
                        return {"error": f"Empty `{k}` for contribution #{idx}!"}
            elif "id" in c:
                collect_ids.append(c["id"])
            elif "project" in c and "identifier" in c:
                project_names.add(c["project"])
            else:
                return {
                    "error": f"Provide `project` & `identifier`, or `id` for contribution #{idx}!"
                }

        id2project = {}
        if collect_ids:
            resp = self.get_all_ids(dict(id__in=collect_ids), timeout=timeout)
            project_names |= set(resp.keys())

            for project_name, values in resp.items():
                for cid in values["ids"]:
                    id2project[cid] = project_name

        existing = defaultdict(dict)
        project_names = list(project_names)

        if len(collect_ids) != len(contributions):
            print("get existing contributions ...")
            unique_identifiers = self.get_unique_identifiers_flags(projects=project_names)
            existing = defaultdict(dict, self.get_all_ids(
                dict(project__in=project_names), include=COMPONENTS, timeout=timeout
            ))

        # prepare contributions
        print("prepare contributions ...")
        contribs = defaultdict(list)
        digests = {project_name: defaultdict(set) for project_name in project_names}
        fields = [
            comp
            for comp in self.get_model("ContributionsSchema")._properties.keys()
            if comp not in COMPONENTS
        ]
        fields.remove("needs_build")  # internal field

        for contrib in tqdm(contributions, leave=False):
            update = "id" in contrib
            project_name = id2project[contrib["id"]] if update else contrib["project"]
            if (
                not update and unique_identifiers[project_name]
                and contrib["identifier"] in existing[project_name].get("identifiers", {})
            ):
                continue

            contribs[project_name].append({
                k: deepcopy(
                    unflatten(contrib[k], splitter="dot")
                    if k == "data" else contrib[k]
                )
                for k in fields if k in contrib
            })

            for component in COMPONENTS:
                elements = contrib.get(component, [])
                nelems = len(elements)

                if nelems > MAX_ELEMS:
                    raise ValueError(f"Too many {component} ({nelems} > {MAX_ELEMS})!")

                if update and not nelems:
                    continue  # nothing to update for this component

                contribs[project_name][-1][component] = []

                for idx, element in enumerate(elements):
                    if update and element is None:
                        contribs[project_name][-1][component].append(None)
                        continue

                    is_structure = isinstance(element, PmgStructure)
                    is_table = isinstance(element, pd.DataFrame)
                    is_attachment = isinstance(element, Path) or isinstance(element, Attachment)
                    if component == "structures" and not is_structure:
                        raise ValueError(f"Use pymatgen Structure for {component}!")
                    elif component == "tables" and not is_table:
                        raise ValueError(f"Use pandas DataFrame for {component}!")
                    elif component == "attachments" and not is_attachment:
                        raise ValueError(
                            f"Use pathlib.Path or mpcontribs.client.Attachment for {component}!"
                        )

                    if is_structure:
                        dct = element.as_dict()
                        del dct["@module"]
                        del dct["@class"]

                        if not dct.get("charge"):
                            del dct["charge"]
                    elif is_table:
                        element.fillna('', inplace=True)
                        element.index = element.index.astype(str)
                        for col in element.columns:
                            element[col] = element[col].astype(str)
                        dct = element.to_dict(orient="split")
                    elif is_attachment:
                        if isinstance(element, Path):
                            kind = guess(str(element))

                            if not isinstance(kind, SUPPORTED_FILETYPES):
                                raise ValueError(
                                    f"{element.name} not supported. Use one of {SUPPORTED_MIMES}!"
                                )

                            content = element.read_bytes()
                            size = len(content)

                            if size > MAX_BYTES:
                                raise ValueError(
                                    f"{element.name} too large ({size} > {MAX_BYTES})!"
                                )

                            dct = {
                                "mime": kind.mime,
                                "content": b64encode(content).decode("utf-8")
                            }
                        else:
                            dct = {k: element[k] for k in ["mime", "content"]}

                    digest = get_md5(dct)

                    if is_structure:
                        dct["name"] = getattr(element, "name", None)
                        if not dct["name"]:
                            c = element.composition
                            comp = c.get_integer_formula_and_factor()
                            dct["name"] = f"{comp[0]}-{idx}" if nelems > 1 else comp[0]
                    elif is_table:
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
                    elif is_attachment:
                        dct["name"] = element.name

                    dupe = bool(
                        digest in digests[project_name][component] or
                        digest in existing[project_name].get(component, {}).get("md5s", set())
                    )

                    if not ignore_dupes and dupe:
                        msg = f"Duplicate in {project_name}: {contrib['identifier']} {dct['name']}"
                        raise ValueError(msg)

                    digests[project_name][component].add(digest)
                    contribs[project_name][-1][component].append(dct)

                valid = self._is_valid_payload("Contribution", contribs[project_name][-1])
                if not valid:
                    return {"error": f"{contrib['identifier']} invalid: {valid}!"}

        # submit contributions
        if contribs:
            if self.session and self.session.executor._shutdown:
                raise ValueError("Session closed. Use `with` statement.")

            print("submit contributions ...")
            total = 0

            def post_future(chunk):
                return self.session.post(
                    f"{self.url}/contributions/",
                    headers=self.headers,
                    data=json.dumps(chunk).encode("utf-8"),
                )

            def put_future(cdct):
                pk = cdct.pop("id")
                return self.session.put(
                    f"{self.url}/contributions/{pk}/",
                    headers=self.headers,
                    data=json.dumps(cdct).encode("utf-8"),
                )

            for project_name in project_names:
                ncontribs = len(contribs[project_name])
                total += ncontribs
                start = datetime.utcnow()

                while contribs[project_name]:
                    futures = []
                    for chunk in grouper(per_page, contribs[project_name]):
                        post_chunk = []
                        for c in chunk:
                            if "id" in c:
                                futures.append(put_future(c))
                            else:
                                post_chunk.append(c)

                        if post_chunk:
                            futures.append(post_future(post_chunk))

                    _run_futures(futures, total=ncontribs, timeout=timeout)

                    if retry and unique_identifiers[project_name]:
                        existing[project_name] = self.get_all_ids(
                            dict(project=project_name), include=COMPONENTS, timeout=timeout
                        ).get(project_name, {"identifiers": set()})
                        unique_identifiers[project_name] = self.projects.get_entry(
                            pk=project_name, _fields=["unique_identifiers"]
                        ).result()["unique_identifiers"]
                        contribs[project_name] = [
                            c for c in contribs[project_name]
                            if c["identifier"] not in existing[project_name]["identifiers"]
                        ]
                    else:
                        contribs[project_name] = []  # abort retrying
                        if retry and not unique_identifiers[project_name]:
                            print("Please resubmit failed contributions manually.")

            end = datetime.utcnow()
            updated_total, _ = self.get_totals(query=dict(
                project__in=project_names, last_modified__after=start, last_modified__before=end
            ), timeout=timeout)
            toc = time.perf_counter()
            dt = (toc - tic) / 60
            self._load()
            print(f"It took {dt:.1f}min to submit {updated_total} contributions.")
        else:
            print("Nothing to submit.")

    def download_contributions(
        self,
        query: dict = None,
        outdir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        overwrite: bool = False,
        include: List[str] = None,
        timeout: int = -1
    ) -> int:
        """Download a list of contributions as .json.gz file(s)

        Args:
            query: query to select contributions
            outdir: optional output directory
            overwrite: force re-download
            include: components to include in downloads
            timeout: cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            Number of new downloads written to disk.
        """
        start = time.perf_counter()
        query = query or {}
        include = include or []
        outdir = Path(outdir) or Path(".")
        outdir.mkdir(parents=True, exist_ok=True)
        components = set(x for x in include if x in COMPONENTS)
        if include and not components:
            print(f"`include` must be subset of {COMPONENTS}!")
            return

        all_ids = self.get_all_ids(query, include=components, timeout=timeout)
        fmt = query.get("format", "json")
        ndownloads = 0

        for name, values in all_ids.items():
            if timeout > 0:
                timeout -= time.perf_counter() - start
                if timeout < 1:
                    return ndownloads

                start = time.perf_counter()

            cids = list(values["ids"])
            paths = self._download_resource(
                resource="contributions", ids=cids, fmt=fmt,
                outdir=outdir, overwrite=overwrite, timeout=timeout
            )
            if paths:
                npaths = len(paths)
                ndownloads += npaths
                print(f"Downloaded {len(cids)} contributions for '{name}' in {npaths} file(s).")
            else:
                print(f"No new contributions to download for '{name}'.")

            for component in components:
                if timeout > 0:
                    timeout -= time.perf_counter() - start
                    if timeout < 1:
                        return ndownloads

                    start = time.perf_counter()

                ids = list(values[component]["ids"])
                paths = self._download_resource(
                    resource=component, ids=ids, fmt=fmt,
                    outdir=outdir, overwrite=overwrite, timeout=timeout
                )
                if paths:
                    npaths = len(paths)
                    ndownloads += npaths
                    print(f"Downloaded {len(ids)} {component} for '{name}' in {npaths} file(s).")
                else:
                    print(f"No new {component} to download for '{name}'.")

        return ndownloads

    def download_structures(
        self,
        ids: List[str],
        outdir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        overwrite: bool = False,
        timeout: int = -1,
        fmt: str = "json"
    ) -> Path:
        """Download a list of structures as a .json.gz file

        Args:
            ids: list of structure ObjectIds
            outdir: optional output directory
            overwrite: force re-download
            timeout: cancel remaining requests if timeout exceeded (in seconds)
            fmt: download format - "json" or "csv"

        Returns:
            paths of output files
        """
        return self._download_resource(
            resource="structures", ids=ids, fmt=fmt,
            outdir=outdir, overwrite=overwrite, timeout=timeout
        )

    def download_tables(
        self,
        ids: List[str],
        outdir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        overwrite: bool = False,
        timeout: int = -1,
        fmt: str = "json"
    ) -> Path:
        """Download a list of tables as a .json.gz file

        Args:
            ids: list of table ObjectIds
            outdir: optional output directory
            overwrite: force re-download
            timeout: cancel remaining requests if timeout exceeded (in seconds)
            fmt: download format - "json" or "csv"

        Returns:
            paths of output files
        """
        return self._download_resource(
            resource="tables", ids=ids, fmt=fmt,
            outdir=outdir, overwrite=overwrite, timeout=timeout
        )

    def download_attachments(
        self,
        ids: List[str],
        outdir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        overwrite: bool = False,
        timeout: int = -1,
        fmt: str = "json"
    ) -> Path:
        """Download a list of attachments as a .json.gz file

        Args:
            ids: list of attachment ObjectIds
            outdir: optional output directory
            overwrite: force re-download
            timeout: cancel remaining requests if timeout exceeded (in seconds)
            fmt: download format - "json" or "csv"

        Returns:
            paths of output files
        """
        return self._download_resource(
            resource="attachments", ids=ids, fmt=fmt,
            outdir=outdir, overwrite=overwrite, timeout=timeout
        )

    def _download_resource(
        self,
        resource: str,
        ids: List[str],
        outdir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        overwrite: bool = False,
        timeout: int = -1,
        fmt: str = "json"
    ) -> Path:
        """Helper to download a list of resources as .json.gz file

        Args:
            resource: type of resource
            ids: list of resource ObjectIds
            outdir: optional output directory
            overwrite: force re-download
            timeout: cancel remaining requests if timeout exceeded (in seconds)
            fmt: download format - "json" or "csv"

        Returns:
            tuple (paths of output files, objects per path / per_page)
        """
        resources = ["contributions"] + COMPONENTS
        if resource not in resources:
            print(f"`resource` must be one of {resources}!")
            return

        formats = {"json", "csv"}
        if fmt not in formats:
            print(f"`fmt` must be one of {formats}!")
            return

        oids = sorted(i for i in ids if ObjectId.is_valid(i))
        outdir = Path(outdir) or Path(".")
        subdir = outdir / resource
        subdir.mkdir(parents=True, exist_ok=True)
        model = self.get_model(f"{resource.capitalize()}Schema")
        fields = list(model._properties.keys())
        query = {"format": fmt, "_fields": fields, "id__in": oids}
        _, total_pages = self.get_totals(
            query=query, resource=resource, op="download", timeout=timeout
        )
        queries = self._split_query(query, resource=resource, op="download", pages=total_pages)
        paths, futures = [], []

        for query in queries:
            digest = get_md5({"ids": query["id__in"].split(",")})
            path = subdir / f"{digest}.{fmt}.gz"

            if not path.exists() or overwrite:
                futures.append(self._get_future(
                    path, query, rel_url=f"{resource}/download/gz"
                ))

        if futures:
            responses = _run_futures(futures, timeout=timeout)

            for path, resp in responses.items():
                path.write_bytes(resp)
                paths.append(path)

        return paths
