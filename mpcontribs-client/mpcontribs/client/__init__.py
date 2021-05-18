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

from typing import Union, Type
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
from ratelimit import limits, sleep_and_retry
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
from filetype.types.archive import Gz
from filetype.types.image import Jpeg, Png, Gif, Tiff
from pint import UnitRegistry, Quantity
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from datetime import datetime

MAX_WORKERS = 10
MAX_ELEMS = 10
MAX_BYTES = 200 * 1024
DEFAULT_HOST = "contribs-api.materialsproject.org"
BULMA = "is-narrow is-fullwidth has-background-light"
PROVIDERS = {"github", "google", "facebook", "microsoft", "amazon"}
COMPONENTS = {"structures", "tables", "attachments"}
VALID_URLS = {f"http://{h}:{p}" for h in ["localhost", "contribs-api"] for p in [5000, 5002, 5003]}
VALID_URLS |= {f"https://{n}-api.materialsproject.org" for n in ["contribs", "lightsources", "ml"]}
VALID_URLS |= {
    f"http://localhost.{n}-api.materialsproject.org" for n in ["contribs", "lightsources", "ml"]
}
SUPPORTED_FILETYPES = (Gz, Jpeg, Png, Gif, Tiff)
SUPPORTED_MIMES = [t().mime for t in SUPPORTED_FILETYPES]

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
            return self.plot(**self.attrs)

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
    # TODO ratelimit support in bravado (wrapped around get_entry..., monkey-patch?)

    _shared_state = {}

    def __init__(self, apikey: str = None, headers: dict = None, host: str = None):
        """Initialize the client - only reloads API spec from server as needed

        Args:
            apikey (str): API key - can also be set via MPCONTRIBS_API_KEY env var
            headers (dict): custom headers for localhost connections - ignored if API key set
            host (str): host address to connect to - can also be set via MPCONTRIBS_API_HOST
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
        self.headers = {"x-api-key": apikey} if apikey else headers
        self.host = host
        ssl = host.endswith(".materialsproject.org") and not host.startswith("localhost.")
        self.protocol = "https" if ssl else "http"
        self.url = f"{self.protocol}://{self.host}"

        if self.url not in VALID_URLS:
            raise ValueError(f"{self.url} not a valid URL (one of {VALID_URLS})")

        if "swagger_spec" not in self.__dict__ or (
            self.swagger_spec.http_client.headers != self.headers
        ):
            self._load()

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
        fields.remove("notebook")
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

        table = {"data": []}
        page, pages = 1, None

        while pages is None or page <= pages:
            resp = self.tables.get_entry(
                pk=tid, _fields=["_all"], data_page=page, data_per_page=1000
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
        ret.attrs = table["attrs"]
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
        units. Use `None` to indicate that a field doesn't have a unit. The unit for a
        dimensionless quantity is an empty string (""). Nested fields are indicated using
        a dot (".") in the data field name. Example:

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
                if col.startswith(k):
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

        resp = self.projects.get_entries(_fields=["name"]).result()
        valid_projects = {p["name"] for p in resp["data"]}

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
                        Quantity(existing_unit).to(new_unit)
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

    def delete_contributions(
        self, name: str, per_page: int = 100, max_workers: int = 5, retry: bool = False
    ):
        """Remove all contributions for a project

        Note: This also resets the columns field for a project. It might have to be
        re-initialized via `client.init_columns()`.

        Args:
            name (str): name of the project for which to delete contributions
            per_page (int): number of contributions to delete per request
            max_workers (int): maximum number of parallel requests to send at a time
            retry (bool): if True, retry deletion of failed contributions until done
        """
        tic = time.perf_counter()

        if max_workers > MAX_WORKERS:
            max_workers = MAX_WORKERS
            print(f"max_workers reset to max {MAX_WORKERS}")

        cids = self.get_contributions(name)["ids"]
        total = len(cids)
        # reset columns to be save (sometimes not all are reset BUGFIX?)
        self.projects.update_entry(pk=name, project={"columns": []}).result()

        if cids:
            with FuturesSession(max_workers=max_workers) as session:
                while cids:
                    futures = [
                        session.delete(
                            f"{self.url}/contributions/",
                            headers=self.headers,
                            params={
                                "project": name,
                                "id__in": ",".join(chunk),
                                "per_page": per_page,
                            },
                        )
                        for chunk in chunks(cids, n=per_page)
                    ]

                    self._run_futures(futures, total=len(cids))
                    cids = self.get_contributions(name)["ids"]

                    if not retry:
                        break

                self._load()

            toc = time.perf_counter()
            dt = (toc - tic) / 60

            if cids:
                print(f"There were errors and {len(cids)} contributions are left to delete!")
            else:
                print(f"It took {dt:.1f}min to delete {total} contributions.")
        else:
            print(f"There aren't any contributions to delete for {name}")

    @sleep_and_retry
    @limits(calls=175, period=60)
    def get_unique_identifiers_flag(self, name: str) -> bool:
        """Retrieve value of `unique_identifiers` flag for a project

        Args:
            name (str): name of the project
        """
        return self.projects.get_entry(
            pk=name, _fields=["unique_identifiers"]
        ).result()["unique_identifiers"]

    @sleep_and_retry
    @limits(calls=175, period=60)
    def get_total_pages(self, name: str, per_page: int) -> int:
        """Retrieve total number of pages for contributions in a project

        Args:
            name (str): name of the project
            per_page (int): number of contributions per page
        """
        return self.contributions.get_entries(
            project=name, per_page=per_page, _fields=["id"],
        ).result()["total_pages"]

    def get_contributions(self, name: str) -> dict:
        """Retrieve a list of existing contributions and their components for a project

        Args:
            name (str): name of the project
        """
        ret = defaultdict(set)
        ret["unique_identifiers"] = self.get_unique_identifiers_flag(name)
        pages = self.get_total_pages(name, 250)
        id_fields = {"id", "identifier"}

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
                    "_fields": ",".join(id_fields | COMPONENTS)
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

                        for component in COMPONENTS:
                            md5s = set(d["md5"] for d in contrib[component])
                            ret[component] |= md5s

                futures = [
                    future
                    for future in futures
                    if future.track_id not in responses.keys()
                ]

        return ret

    def update_contributions(self, name: str, data: dict, query: dict = None) -> dict:
        """Apply the same update to all contributions in a project (matching query)

        See `client.contributions.get_entries()` for keyword arguments used in query.

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

        query = query or {}
        query["project"] = name
        has_more = True
        updated = 0

        while has_more:
            resp = self.contributions.update_entries(
                contributions=data, _limit=250, **query
            ).result()
            has_more = resp["has_more"]
            updated += resp["count"]

        print(f"Updated {updated} contributions.")

    def get_number_contributions(self, **query) -> int:
        """Retrieve total number of contributions for query

        See `client.contributions.get_entries()` for keyword arguments used in query.
        """
        return self.contributions.get_entries(
            _fields=["id"], _limit=1, **query
        ).result()["total_count"]

    def publish(self, name: str, recursive: bool = False) -> dict:
        """Publish a project and optionally its contributions

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
        contributions: list,
        skip_dupe_check: bool = False,
        ignore_dupes: bool = False,
        retry: bool = False,
        per_page: int = 100,
        max_workers: int = 3,
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
            skip_dupe_check (bool): skip check for duplicates of identifiers and components
            ignore_dupes (bool): force duplicate components to be submitted
            retry (bool): keep trying until all contributions successfully submitted
            per_page (int): number of contributions to submit in each chunk/request
            max_workers (int): number of parallel requests to use to submit chunk
        """
        if not contributions or not isinstance(contributions, list):
            print("Please provide list of contributions to submit.")
            return

        tic = time.perf_counter()

        if max_workers > MAX_WORKERS:
            max_workers = MAX_WORKERS
            print(f"max_workers reset to max {MAX_WORKERS}")

        # get existing contributions
        existing = defaultdict(set)
        existing["unique_identifiers"] = True
        project_names = set()
        collect_ids = []
        require_one_of = {"data"} | COMPONENTS

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
            resp = self.contributions.get_entries(
                id__in=collect_ids, _fields=["id", "project"]
            ).result()
            id2project = {c["id"]: c["project"] for c in resp["data"]}
            project_names |= set(id2project.values())

        project_names = list(project_names)

        if not skip_dupe_check:
            print("get existing contributions ...")
            existing = {
                project_name: self.get_contributions(project_name)
                for project_name in project_names
            }

        # prepare contributions
        print("prepare contributions ...")
        contribs = defaultdict(list)
        digests = {project_name: defaultdict(set) for project_name in project_names}
        fields = [
            comp
            for comp in self.get_model("ContributionsSchema")._properties.keys()
            if comp not in COMPONENTS
        ]

        for contrib in tqdm(contributions, leave=False):
            update = "id" in contrib
            project_name = id2project[contrib["id"]] if update else contrib["project"]
            if (
                not update and existing[project_name]["unique_identifiers"]
                and contrib["identifier"] in existing[project_name]["identifiers"]
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
                        digest in existing[project_name][component]
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
            print("submit contributions ...")
            with FuturesSession(max_workers=max_workers) as session:
                # bravado future doesn't work with concurrent.futures
                total = 0
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

                def put_future(cdct):
                    pk = cdct.pop("id")
                    return session.put(
                        f"{self.url}/contributions/{pk}/",
                        headers=headers,
                        data=json.dumps(cdct).encode("utf-8"),
                    )

                for project_name in project_names:
                    ncontribs = len(contribs[project_name])
                    total += ncontribs
                    start = datetime.utcnow()

                    while contribs[project_name]:
                        futures = []
                        for chunk in chunks(contribs[project_name], n=per_page):
                            post_chunk = []
                            for c in chunk:
                                if "id" in c:
                                    futures.append(put_future(c))
                                else:
                                    post_chunk.append(c)

                            if post_chunk:
                                futures.append(post_future(post_chunk))

                        self._run_futures(futures, total=ncontribs)

                        if existing[project_name]["unique_identifiers"] and retry:
                            existing[project_name] = self.get_contributions(project_name)
                            contribs[project_name] = [
                                c for c in contribs[project_name]
                                if c["identifier"] not in existing[project_name]["identifiers"]
                            ]
                        else:
                            contribs[project_name] = []  # abort retrying
                            if not existing[project_name]["unique_identifiers"] and retry:
                                print("Please resubmit failed contributions manually.")

                end = datetime.utcnow()
                updated_total = self.get_number_contributions(
                    project__in=project_names, last_modified__gt=start, last_modified__lt=end
                )
                toc = time.perf_counter()
                dt = (toc - tic) / 60
                self._load()
                print(f"It took {dt:.1f}min to submit {updated_total} contributions.")
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
                        if total and "data" in resp:
                            cnt = len(resp["data"])
                        elif total and "count" in resp:
                            cnt = resp["count"]
                        else:
                            cnt = 1
                        pbar.update(cnt)
                        if hasattr(future, "track_id"):
                            responses[future.track_id] = resp
                        if "warning" in resp:
                            print(resp["warning"])
                    elif status != 502:
                        print(resp["error"][:10000] + "...")
                elif status not in {503, 504}:
                    print("ERROR", response.content.decode("utf-8"))

        return responses
