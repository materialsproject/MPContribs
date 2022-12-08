# -*- coding: utf-8 -*-
import io
import sys
import os
import ujson
import time
import gzip
import warnings
import pandas as pd
import plotly.io as pio
import itertools
import functools
import requests
import logging
import datetime

from semantic_version import Version
from requests.exceptions import RequestException
from bravado_core.param import Param
from bson.objectid import ObjectId
from typing import Union, Type, List
from tqdm.auto import tqdm
from hashlib import md5
from pathlib import Path
from copy import deepcopy
from filetype import guess
from flatten_dict import flatten, unflatten
from base64 import b64encode, b64decode, urlsafe_b64encode
from urllib.parse import urlparse
from pyisemail import is_email
from collections import defaultdict
from pyisemail.diagnosis import BaseDiagnosis
from swagger_spec_validator.common import SwaggerValidationError
from jsonschema.exceptions import ValidationError
from bravado_core.formatter import SwaggerFormat
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
from bravado.swagger_model import Loader
from bravado.config import bravado_config_from_config_dict
from bravado_core.spec import Spec
from bravado.exception import HTTPNotFound
from bravado_core.validate import validate_object
from json2html import Json2Html
from IPython.display import display, HTML, Image, FileLink
from boltons.iterutils import remap
from pymatgen.core import Structure as PmgStructure
from concurrent.futures import as_completed, ProcessPoolExecutor
from requests_futures.sessions import FuturesSession
from urllib3.util.retry import Retry
from filetype.types.archive import Gz
from filetype.types.image import Jpeg, Png, Gif, Tiff
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from tempfile import gettempdir

RETRIES = 3
MAX_WORKERS = 8
MAX_ELEMS = 10
MAX_NESTING = 5
MEGABYTES = 1024 * 1024
MAX_BYTES = 2.4 * MEGABYTES
MAX_PAYLOAD = 15 * MEGABYTES
MAX_COLUMNS = 160
DEFAULT_HOST = "contribs-api.materialsproject.org"
BULMA = "is-narrow is-fullwidth has-background-light"
PROVIDERS = {"github", "google", "facebook", "microsoft", "amazon"}
COMPONENTS = ["structures", "tables", "attachments"]  # using list to maintain order
SUBDOMAINS = ["contribs", "lightsources", "ml", "workshop-contribs"]
PORTS = [5000, 5002, 5003, 5005, 10000, 10002, 10003, 10005, 20000]
HOSTS = ["localhost", "contribs-apis"]
HOSTS += [f"192.168.0.{i}" for i in range(36, 47)]  # PrivateSubnetOne
HOSTS += [f"192.168.0.{i}" for i in range(52, 63)]  # PrivateSubnetTwo
VALID_URLS = {f"http://{h}:{p}" for p in PORTS for h in HOSTS}
VALID_URLS |= {
    f"https://{n}-api{m}.materialsproject.org"
    for n in SUBDOMAINS for m in ["", "-preview"]
}
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

LOG_LEVEL = os.environ.get("MPCONTRIBS_CLIENT_LOG_LEVEL", "INFO")
log_level = getattr(logging, LOG_LEVEL.upper())
_session = requests.Session()
_executor = ProcessPoolExecutor(max_workers=MAX_WORKERS)


class LogFilter(logging.Filter):
    def __init__(self, level, *args, **kwargs):
        self.level = level
        super(LogFilter, self).__init__(*args, **kwargs)

    def filter(self, record):
        return record.levelno < self.level


class CustomLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        prefix = self.extra.get('prefix')
        return f"[{prefix}] {msg}" if prefix else msg, kwargs


class TqdmToLogger(io.StringIO):
    logger = None
    level = None
    buf = ''

    def __init__(self, logger, level=None):
        super(TqdmToLogger, self).__init__()
        self.logger = logger
        self.level = level or logging.INFO

    def write(self, buf):
        self.buf = buf.strip('\r\n\t ')

    def flush(self):
        self.logger.log(self.level, self.buf)


def get_logger(name):
    logger = logging.getLogger(name)
    process = os.environ.get("SUPERVISOR_PROCESS_NAME")
    group = os.environ.get("SUPERVISOR_GROUP_NAME")
    cfg = {"prefix": f"{group}/{process}"} if process and group else {}
    info_handler = logging.StreamHandler(sys.stdout)
    error_handler = logging.StreamHandler(sys.stderr)
    info_handler.addFilter(LogFilter(logging.WARNING))
    error_handler.setLevel(max(logging.DEBUG, logging.WARNING))
    logger.handlers = [info_handler, error_handler]
    logger.setLevel(log_level)
    return CustomLoggerAdapter(logger, cfg)


logger = get_logger(__name__)
tqdm_out = TqdmToLogger(logger, level=log_level)


def get_md5(d):
    s = ujson.dumps(d, sort_keys=True).encode("utf-8")
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


def get_session(session=None):
    # TODO add Bad Gateway 502?
    adapter_kwargs = dict(max_retries=Retry(
        total=RETRIES,
        read=RETRIES,
        connect=RETRIES,
        respect_retry_after_header=True,
        status_forcelist=[429],  # rate limit
    ))
    s = session if session else _session
    futures_session = FuturesSession(
        session=s, executor=_executor, adapter_kwargs=adapter_kwargs
    )
    futures_session.hooks['response'].append(_response_hook)
    return futures_session


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
            logger.warning(result["warning"])
        elif "error" in result and isinstance(result["error"], str):
            logger.error(result["error"][:10000] + "...")

    elif content_type == "application/gzip":
        resp.result = resp.content
        resp.count = 1
    else:
        logger.error(f"request failed with status {resp.status_code}!")
        resp.count = 0


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
                logger.error(f"Can't display table: {e}")

        return self

    def info(self) -> Type[Dict]:
        """Show summary info for table"""
        info = Dict((k, v) for k, v in self.attrs.items())
        info["columns"] = ", ".join(self.columns)
        info["nrows"] = len(self.total_data_rows)
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

    def unpack(self) -> str:
        unpacked = self.decode()

        if self["mime"] == "application/gzip":
            unpacked = gzip.decompress(unpacked).decode("utf-8")

        return unpacked

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
        data_json = ujson.dumps(data, indent=4).encode("utf-8")
        content = gzip.compress(data_json)
        size = len(content)

        if size > MAX_BYTES:
            raise ValueError(f"{name} too large ({size} > {MAX_BYTES})!")

        return cls(
            name=filename,
            mime="application/gzip",
            content=b64encode(content).decode("utf-8")
        )


def _run_futures(futures, total: int = 0, timeout: int = -1, desc=None, disable=False):
    """helper to run futures/requests"""
    start = time.perf_counter()
    total_set = total > 0
    total = total if total_set else len(futures)
    responses = {}

    with tqdm(
        total=total, desc=desc, file=tqdm_out, miniters=1, delay=5, disable=disable
    ) as pbar:
        for future in as_completed(futures):
            if not future.cancelled():
                response = future.result()
                cnt = response.count if total_set and hasattr(response, "count") else 1
                pbar.update(cnt)

                if hasattr(future, "track_id"):
                    tid = future.track_id
                    responses[tid] = {}
                    if hasattr(response, "result"):
                        responses[tid]["result"] = response.result
                    if hasattr(response, "count"):
                        responses[tid]["count"] = response.count

                elapsed = time.perf_counter() - start
                timed_out = timeout > 0 and elapsed > timeout

                if timed_out or not response.ok:
                    for fut in futures:
                        fut.cancel()

    return responses


@functools.lru_cache(maxsize=1000)
def _load(protocol, host, headers_json, project, version):
    headers = ujson.loads(headers_json)
    http_client = RequestsClient()
    http_client.session.headers.update(headers)
    url = f"{protocol}://{host}"
    origin_url = f"{url}/apispec.json"
    url4fn = origin_url.replace("apispec", f"apispec-{version}").encode('utf-8')
    fn = urlsafe_b64encode(url4fn).decode('utf-8')
    apispec = Path(gettempdir()) / fn
    spec_dict = None

    if apispec.exists():
        spec_dict = ujson.loads(apispec.read_bytes())
        logger.debug(f"Specs for {origin_url} and {version} re-loaded from {apispec}.")
    else:
        loader = Loader(http_client)
        spec_dict = loader.load_spec(origin_url)

        with apispec.open("w") as f:
            ujson.dump(spec_dict, f)

        logger.debug(f"Specs for {origin_url} and {version} saved as {apispec}.")

    if not spec_dict:
        raise ValueError(f"Could not load specs from {url} for {version}!")  # not cached

    spec_dict["host"] = host
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

    if not spec_dict["paths"]:
        return swagger_spec

    # expand regex-based query parameters for `data` columns
    query = {"name": project} if project else {}
    query["_fields"] = ["columns"]
    kwargs = dict(headers=headers, params=query)
    resp = _session.get(f"{url}/projects/", **kwargs).json()

    if not resp or not resp["data"]:
        raise ValueError(f"Failed to load projects for query {query}!")

    if project and not resp["data"]:
        raise ValueError(f"{project} doesn't exist, or access denied!")

    columns = {"string": [], "number": []}

    for proj in resp["data"]:
        for column in proj["columns"]:
            if column["path"].startswith("data."):
                col = column["path"].replace(".", "__")
                if column["unit"] == "NaN":
                    columns["string"].append(col)
                else:
                    col = f"{col}__value"
                    columns["number"].append(col)

    resource = swagger_spec.resources["contributions"]

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
                    param_spec.pop("description", None)
                    operation.params[param_name] = Param(
                        swagger_spec, operation, param_spec
                    )

    return swagger_spec


@functools.lru_cache(maxsize=1)
def _version(url):
    retries, max_retries = 0, 3
    protocol = urlparse(url).scheme
    is_mock_test = 'pytest' in sys.modules and protocol == "http"

    if is_mock_test:
        now = datetime.datetime.now()
        return Version(
            major=now.year, minor=now.month, patch=now.day,
            prerelease=(str(now.hour), str(now.minute))
        )
    else:
        while retries < max_retries:
            try:
                r = requests.get(f"{url}/healthcheck", timeout=2)
                if r.status_code == 200:
                    return r.json().get("version")
                else:
                    retries += 1
                    logger.warning(
                        f"Healthcheck for {url} failed ({r.status_code})! Wait 30s."
                    )
                    time.sleep(30)
            except RequestException as ex:
                retries += 1
                logger.warning(f"Could not connect to {url} ({ex})! Wait 30s.")
                time.sleep(30)


class Client(SwaggerClient):
    """client to connect to MPContribs API

    Typical usage:
        - set environment variable MPCONTRIBS_API_KEY to the API key from your MP profile
        - import and init:
          >>> from mpcontribs.client import Client
          >>> client = Client()
    """
    def __init__(
        self,
        apikey: str = None,
        headers: dict = None,
        host: str = None,
        project: str = None,
        session: requests.Session = None,
    ):
        """Initialize the client - only reloads API spec from server as needed

        Args:
            apikey (str): API key (or use MPCONTRIBS_API_KEY env var) - ignored if headers set
            headers (dict): custom headers for localhost connections
            host (str): host address to connect to (or use MPCONTRIBS_API_HOST env var)
            project (str): use this project for all operations (query, update, create, delete)
            session (requests.Session): override session for client to use
        """
        # NOTE bravado future doesn't work with concurrent.futures
        # - Kong forwards consumer headers when api-key used for auth
        # - forward consumer headers when connecting through localhost
        if not host:
            host = os.environ.get("MPCONTRIBS_API_HOST", DEFAULT_HOST)

        if not apikey:
            apikey = os.environ.get("MPCONTRIBS_API_KEY")

        if apikey and headers is not None:
            apikey = None
            logger.debug("headers set => ignoring apikey!")

        self.apikey = apikey
        self.headers = headers or {}
        self.headers = {"x-api-key": apikey} if apikey else self.headers
        self.headers["Content-Type"] = "application/json"
        self.headers_json = ujson.dumps(self.headers, sort_keys=True)
        self.host = host
        ssl = host.endswith(".materialsproject.org") and not host.startswith("localhost.")
        self.protocol = "https" if ssl else "http"
        self.url = f"{self.protocol}://{self.host}"
        self.project = project

        if self.url not in VALID_URLS:
            raise ValueError(f"{self.url} not a valid URL (one of {VALID_URLS})")

        self.version = _version(self.url)  # includes healthcheck
        self.session = get_session(session=session)
        super().__init__(self.cached_swagger_spec)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    @property
    def cached_swagger_spec(self):
        return _load(self.protocol, self.host, self.headers_json, self.project, self.version)

    def __dir__(self):
        members = set(self.swagger_spec.resources.keys())
        members |= set(k for k in self.__dict__.keys() if not k.startswith("_"))
        members |= set(k for k in dir(self.__class__) if not k.startswith("_"))
        return members

    def _reinit(self):
        _load.cache_clear()
        super().__init__(self.cached_swagger_spec)

    def _is_valid_payload(self, model: str, data: dict):
        model_spec = deepcopy(self.get_model(f"{model}sSchema")._model_spec)
        model_spec.pop("required")
        model_spec['additionalProperties'] = False

        try:
            validate_object(self.swagger_spec, model_spec, data)
        except ValidationError as ex:
            return False, str(ex)

        return True, None

    def _is_serializable_dict(self, dct):
        for k, v in flatten(dct, reducer="dot").items():
            if v is not None and not isinstance(v, (str, int, float)):
                error = f"Value {v} of {type(v)} for key {k} not supported."
                return False, error

        return True, None

    def _get_per_page_default_max(self, op: str = "query", resource: str = "contributions") -> int:
        resource = self.swagger_spec.resources[resource]
        attr = f"{op}{resource.capitalize()}"
        param_spec = getattr(resource, attr).params["per_page"].param_spec
        return param_spec["default"], param_spec["maximum"]

    def _get_per_page(
        self, per_page: int, op: str = "query", resource: str = "contributions"
    ) -> int:
        _, per_page_max = self._get_per_page_default_max(op=op, resource=resource)
        return min(per_page_max, per_page)

    def _split_query(
        self,
        query: dict,
        op: str = "query",
        resource: str = "contributions",
        pages: int = -1,
    ) -> List[dict]:
        """Avoid URI too long errors"""
        pp_default, pp_max = self._get_per_page_default_max(op=op, resource=resource)
        per_page = pp_default if any(k.endswith("__in") for k in query.keys()) else pp_max
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
        op: str = "query",
        data: dict = None
    ):
        rname = rel_url.split("/", 1)[0]
        resource = self.swagger_spec.resources[rname]
        attr = f"{op}{resource.capitalize()}"
        method = getattr(resource, attr).http_method
        kwargs = dict(headers=self.headers, params=params)

        if method == "put" and data:
            kwargs["data"] = ujson.dumps(data).encode("utf-8")

        future = getattr(self.session, method)(
            f"{self.url}/{rel_url}/", **kwargs
        )
        setattr(future, "track_id", track_id)
        return future

    def get_project(self, name: str = None) -> Type[Dict]:
        """Retrieve full project entry

        Args:
            name (str): name of the project
        """
        name = self.project or name
        if not name:
            return {"error": "initialize client with project or set `name` argument!"}

        return Dict(self.projects.getProjectByName(pk=name, _fields=["_all"]).result())

    def create_project(self, name: str, title: str, authors: str, description: str, url: str):
        """Create a project

        Args:
            name (str): unique name matching `^[a-zA-Z0-9_]{3,31}$`
            title (str): unique title with 5-30 characters
            authors (str): comma-separated list of authors
            description (str): brief description (max 1500 characters)
            url (str): URL for primary reference (paper/website/...)
        """
        queries = [{"name": name}, {"title": title}]
        for query in queries:
            if self.get_totals(query=query, resource="projects")[0]:
                logger.error(f"Project with {query} already exists!")
                return

        project = {
            "name": name, "title": title, "authors": authors, "description": description,
            "references": [{"label": "REF", "url": url}]
        }
        owner = self.projects.createProject(project=project).result().get("owner")
        logger.info(f"Project `{name}` created with owner `{owner}`")

    def get_contribution(self, cid: str) -> Type[Dict]:
        """Retrieve full contribution entry

        Args:
            cid (str): contribution ObjectID
        """
        fields = list(self.get_model("ContributionsSchema")._properties.keys())
        fields.remove("needs_build")  # internal field
        return Dict(self.contributions.getContributionById(pk=cid, _fields=fields).result())

    def get_table(self, tid_or_md5: str) -> Type[Table]:
        """Retrieve full Pandas DataFrame for a table

        Args:
            tid_or_md5 (str): ObjectId or MD5 hash digest for table
        """
        str_len = len(tid_or_md5)
        if str_len not in {24, 32}:
            raise ValueError(f"'{tid_or_md5}' is not a valid table id or md5 hash digest!")

        if str_len == 32:
            tables = self.tables.queryTables(md5=tid_or_md5, _fields=["id"]).result()
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
            resp = self.tables.getTableById(
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
            structures = self.structures.queryStructures(md5=sid_or_md5, _fields=["id"]).result()
            if not structures:
                raise ValueError(f"structure for md5 '{sid_or_md5}' not found!")
            sid = structures["data"][0]["id"]
        else:
            sid = sid_or_md5

        fields = list(self.get_model("StructuresSchema")._properties.keys())
        resp = self.structures.getStructureById(pk=sid, _fields=fields).result()
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
            attachments = self.attachments.queryAttachments(
                md5=aid_or_md5, _fields=["id"]
            ).result()
            if not attachments:
                raise ValueError(f"attachment for md5 '{aid_or_md5}' not found!")
            aid = attachments["data"][0]["id"]
        else:
            aid = aid_or_md5

        return Attachment(self.attachments.getAttachmentById(pk=aid, _fields=["_all"]).result())

    def init_columns(self, columns: dict = None) -> dict:
        """initialize columns for a project to set their order and desired units

        The `columns` field of a project tracks the minima and maxima of each `data` field
        in its contributions. If columns are not initialized before submission using this
        function, `submit_contributions` will respect the order of columns as they are
        submitted and will try to auto-determine suitable units.

        `init_columns` can be used at any point to reset the order of columns. Omitting
        the `columns` argument will re-initialize columns based on the `data` fields of
        all submitted contributions.

        The `columns` argument is a dictionary which maps the data field names to its
        units. Use `None` to indicate that a field is not a quantity (plain string). The
        unit for a dimensionless quantity is an empty string (""). Percent (`%`) and
        permille (`%%`) are considered units. Nested fields are indicated using a dot
        (".") in the data field name.

        Example:

        >>> client.init_columns({"a": None, "b.c": "eV", "b.d": "mm", "e": ""})

        This example will result in column headers on the project landing page of the form


        |      |      data       |      |
        | data |        b        | data |
        |   a  | c [eV] | d [mm] | e [] |


        Args:
            columns (dict): dictionary mapping data column to its unit
        """
        if not self.project:
            return {"error": "initialize client with project argument!"}

        columns = flatten(columns or {}, reducer="dot")

        if len(columns) > MAX_COLUMNS:
            return {"error": f"Number of columns larger than {MAX_COLUMNS}!"}

        if not all(isinstance(v, str) for v in columns.values() if v is not None):
            return {"error": "All values in `columns` need to be None or of type str!"}

        new_columns = []

        if columns:
            # check columns input
            scanned_columns = set()

            for k, v in columns.items():
                if k in COMPONENTS:
                    scanned_columns.add(k)
                    continue

                nesting = k.count(".")
                if nesting > MAX_NESTING:
                    return {"error": f"Nesting depth larger than {MAX_NESTING} for {k}!"}

                for col in scanned_columns:
                    if nesting and col.startswith(k):
                        return {"error": f"Duplicate definition of {k} in {col}!"}

                    for n in range(1, nesting+1):
                        if k.rsplit(".", n)[0] == col:
                            return {"error": f"Ancestor of {k} already defined in {col}!"}

                is_valid_string = isinstance(v, str) and v.lower() != "nan"
                if not is_valid_string and v is not None:
                    return {
                        "error": f"Unit '{v}' for {k} invalid (use `None` or a non-NaN string)!"
                    }

                if v != "" and v is not None and v not in ureg:
                    return {"error": f"Unit '{v}' for {k} invalid!"}

                scanned_columns.add(k)

            # sort to avoid "overlapping columns" error in handsontable's NestedHeaders
            sorted_columns = flatten(unflatten(columns, splitter="dot"), reducer="dot")

            # reconcile with existing columns
            resp = self.projects.getProjectById(pk=self.project, _fields=["columns"]).result()
            existing_columns = {}

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
        valid, error = self._is_valid_payload("Project", payload)
        if not valid:
            return {"error": error}

        return self.projects.updateProjectByName(pk=self.project, project=payload).result()

    def delete_contributions(self, query: dict = None, timeout: int = -1):
        """Remove all contributions for a query

        Args:
            query (dict): optional query to select contributions
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        if not self.project and (not query or "project" not in query):
            logger.error("initialize client with project, or include project in query!")
            return

        tic = time.perf_counter()
        query = query or {}

        if self.project:
            query["project"] = self.project

        cids = list(self.get_all_ids(query).get(query["project"], {}).get("ids", set()))

        if not cids:
            logger.info(f"There aren't any contributions to delete for {query['project']}")
            return

        total = len(cids)
        query = {"id__in": cids}
        _, total_pages = self.get_totals(query=query)
        queries = self._split_query(query, op="delete", pages=total_pages)
        futures = [self._get_future(i, q, op="delete") for i, q in enumerate(queries)]
        _run_futures(futures, total=total, timeout=timeout)
        left, _ = self.get_totals(query=query)
        deleted = total - left
        self.init_columns()
        self._reinit()
        toc = time.perf_counter()
        dt = (toc - tic) / 60
        logger.info(f"It took {dt:.1f}min to delete {deleted} contributions.")

        if left:
            logger.error(f"There were errors and {left} contributions are left to delete!")

    def get_totals(
        self,
        query: dict = None,
        timeout: int = -1,
        resource: str = "contributions",
        op: str = "query"
    ) -> tuple:
        """Retrieve total count and pages for resource entries matching query

        Args:
            query (dict): query to select resource entries
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
            resource (str): type of resource
            op (str): operation to calculate total pages for, one of
                      ("query", "create", "update", "delete", "download")

        Returns:
            tuple of total counts and pages
        """
        ops = {"query", "create", "update", "delete", "download"}
        if op not in ops:
            logger.error(f"`op` has to be one of {ops}")
            return

        query = query or {}
        if self.project and "project" not in query:
            query["project"] = self.project

        skip_keys = {"per_page", "_fields", "format", "_sort"}
        query = {k: v for k, v in query.items() if k not in skip_keys}
        query["_fields"] = []  # only need totals -> explicitly request no fields
        queries = self._split_query(query, resource=resource, op=op)  # don't paginate
        result = {"total_count": 0, "total_pages": 0}
        futures = [self._get_future(i, q, rel_url=resource) for i, q in enumerate(queries)]
        responses = _run_futures(futures, timeout=timeout, desc="Totals")

        for resp in responses.values():
            for k in result:
                result[k] += resp.get("result", {}).get(k, 0)

        return result["total_count"], result["total_pages"]

    def get_unique_identifiers_flags(self, projects: list = None) -> dict:
        """Retrieve values for `unique_identifiers` flags for a list of projects

        Args:
            projects (list): list of project names - return all if not set

        Returns:
            {"<project-name>": True|False, ...}
        """
        unique_identifiers, query = {}, {}

        if projects:
            query = {"name__in": projects}
        elif self.project:
            query = {"name": self.project}

        resp = self.projects.queryProjects(
            _fields=["name", "unique_identifiers"], **query
        ).result()

        for project in resp["data"]:
            project_name = project["name"]
            unique_identifiers[project_name] = project["unique_identifiers"]

        return unique_identifiers

    def get_all_ids(
        self,
        query: dict = None,
        include: List[str] = None,
        timeout: int = -1,
        data_id_fields: dict = None,
        fmt: str = "sets",
        op: str = "query",
    ) -> dict:
        """Retrieve a list of existing contribution and component (Object)IDs

        Args:
            query (dict): query to select contributions
            include (list): components to include in response
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
            data_id_fields (dict): map of project to extra field in `data` to include as ID field
            fmt (str): return `sets` of identifiers or `map` (see below)
            op (str): operation to calculate total pages for, one of
                      ("query", "create", "update", "delete", "download")

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
            logger.error(f"`include` must be subset of {COMPONENTS}!")
            return

        fmts = {"sets", "map"}
        if fmt not in fmts:
            logger.error(f"`fmt` must be subset of {fmts}!")
            return

        ops = {"query", "create", "update", "delete", "download"}
        if op not in ops:
            logger.error(f"`op` has to be one of {ops}")
            return

        unique_identifiers = self.get_unique_identifiers_flags()
        data_id_fields = {
            k: v for k, v in data_id_fields.items()
            if k in unique_identifiers and isinstance(v, str)
        } if data_id_fields else {}

        ret = {}
        query = query or {}
        if self.project and "project" not in query:
            query["project"] = self.project

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
        responses = _run_futures(futures, timeout=timeout, desc="Identifiers")

        for resp in responses.values():
            for contrib in resp["result"]["data"]:
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

    def query_contributions(
        self,
        query: dict = None,
        fields: list = None,
        sort: str = None,
        paginate: bool = False,
        timeout: int = -1
    ) -> List[dict]:
        """Query contributions

        See `client.contributions.queryContributions()` for keyword arguments used in query.

        Args:
            query (dict): optional query to select contributions
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            paginate (bool): paginate through all results
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of contributions
        """
        query = query or {}

        if self.project and "project" not in query:
            query["project"] = self.project

        if paginate:
            cids = []

            for v in self.get_all_ids(query).values():
                cids_project = v.get("ids")
                if cids_project:
                    cids.extend(cids_project)

            if not cids:
                return {"error": "No contributions match the query."}

            total = len(cids)
            cids_query = {"id__in": cids, "_fields": fields, "_sort": sort}
            _, total_pages = self.get_totals(query=cids_query)
            queries = self._split_query(cids_query, pages=total_pages)
            futures = [self._get_future(i, q) for i, q in enumerate(queries)]
            responses = _run_futures(futures, total=total, timeout=timeout)
            ret = {"total_count": 0, "data": []}

            for resp in responses.values():
                result = resp["result"]
                ret["data"].extend(result["data"])
                ret["total_count"] += result["total_count"]
        else:
            ret = self.contributions.queryContributions(
                _fields=fields, _sort=sort, **query
            ).result()

        return ret

    def update_contributions(
        self,
        data: dict,
        query: dict = None,
        timeout: int = -1
    ) -> dict:
        """Apply the same update to all contributions in a project (matching query)

        See `client.contributions.queryContributions()` for keyword arguments used in query.

        Args:
            data (dict): update to apply on every matching contribution
            query (dict): optional query to select contributions
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        if not data:
            return "Nothing to update."

        tic = time.perf_counter()
        valid, error = self._is_valid_payload("Contribution", data)
        if not valid:
            return {"error": error}

        if "data" in data:
            serializable, error = self._is_serializable_dict(data["data"])
            if not serializable:
                return {"error": error}

        query = query or {}

        if not self.project and (not query or "project" not in query):
            return {"error": "initialize client with project, or include project in query!"}

        if "project" in query and self.project != query["project"]:
            return {"error": f"client initialized with different project {self.project}!"}

        query["project"] = self.project
        cids = list(self.get_all_ids(query).get(self.project, {}).get("ids", set()))

        if not cids:
            logger.info(f"There aren't any contributions to update for {self.project}")
            return

        # get current list of data columns to decide if swagger reload is needed
        resp = self.projects.getProjectByName(pk=self.project, _fields=["columns"]).result()
        old_paths = set(c["path"] for c in resp["columns"])

        total = len(cids)
        cids_query = {"id__in": cids}
        _, total_pages = self.get_totals(query=cids_query)
        queries = self._split_query(cids_query, op="update", pages=total_pages)
        futures = [
            self._get_future(i, q, op="update", data=data)
            for i, q in enumerate(queries)
        ]
        responses = _run_futures(futures, total=total, timeout=timeout)
        updated = sum(resp["count"] for _, resp in responses.items())

        if updated:
            resp = self.projects.getProjectByName(pk=self.project, _fields=["columns"]).result()
            new_paths = set(c["path"] for c in resp["columns"])

            if new_paths != old_paths:
                self.init_columns()
                self._reinit()

        toc = time.perf_counter()
        return {"updated": updated, "total": total, "seconds_elapsed": toc - tic}

    def make_public(
        self,
        query: dict = None,
        recursive: bool = False,
        timeout: int = -1
    ) -> dict:
        """Publish a project and optionally its contributions

        Args:
            query (dict): optional query to select contributions
            recursive (bool): also publish according contributions?
        """
        return self._set_is_public(
            True, query=query, recursive=recursive, timeout=timeout
        )

    def make_private(
        self,
        query: dict = None,
        recursive: bool = False,
        timeout: int = -1
    ) -> dict:
        """Make a project and optionally its contributions private

        Args:
            query (dict): optional query to select contributions
            recursive (bool): also make according contributions private?
        """
        return self._set_is_public(
            False, query=query, recursive=recursive, timeout=timeout
        )

    def _set_is_public(
        self,
        is_public: bool,
        query: dict = None,
        recursive: bool = False,
        timeout: int = -1
    ) -> dict:
        """Set the `is_public` flag for a project and optionally its contributions

        Args:
            is_public (bool): target value for `is_public` flag
            query (dict): optional query to select contributions
            recursive (bool): also set `is_public` for according contributions?
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        if not self.project and (not query or "project" not in query):
            return {"error": "initialize client with project, or include project in query!"}

        query = query or {}

        if self.project:
            query["project"] = self.project

        try:
            resp = self.projects.getProjectByName(
                pk=query["project"], _fields=["is_public", "is_approved"]
            ).result()
        except HTTPNotFound:
            return {"error": f"project `{query['project']}` not found or access denied!"}

        if not recursive and resp["is_public"] == is_public:
            return {"warning": f"`is_public` already set to {is_public} for `{query['project']}`."}

        ret = {}

        if resp["is_public"] != is_public:
            if is_public and not resp["is_approved"]:
                return {"error": f"project `{query['project']}` is not approved yet!"}

            resp = self.projects.updateProjectByName(
                pk=query["project"], project={"is_public": is_public}
            ).result()
            ret["published"] = resp["is_public"] == is_public

        if recursive:
            query = query or {}
            query["is_public"] = not is_public
            ret["contributions"] = self.updateContributions(
                {"is_public": is_public}, query=query, timeout=timeout
            )

        return ret

    def submit_contributions(
        self,
        contributions: List[dict],
        ignore_dupes: bool = False,
        retry: bool = False,
        per_request: int = 100,
        timeout: int = -1,
        skip_dupe_check: bool = False
    ):
        """Submit a list of contributions

        Example for a single contribution dictionary:

        {
            "project": "sandbox",
            "identifier": "mp-4",
            "data": {
                "a": "3 eV",
                "b": {"c": "hello", "d": 3}
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
            skip_dupe_check (bool): skip duplicate check for contribution identifiers
        """
        if not contributions or not isinstance(contributions, list):
            logger.error("Please provide list of contributions to submit.")
            return

        # get existing contributions
        tic = time.perf_counter()
        project_names = set()
        collect_ids = []
        require_one_of = {"data"} | set(COMPONENTS)
        per_page = self._get_per_page(per_request)

        for idx, contrib in enumerate(contributions):
            c = contributions[idx] = unflatten(contrib, splitter="dot")
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
            elif self.project and "project" not in c and "identifier" in c:
                project_names.add(self.project)
                contributions[idx]["project"] = self.project
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
        unique_identifiers = defaultdict(dict)
        project_names = list(project_names)

        if not skip_dupe_check and len(collect_ids) != len(contributions):
            unique_identifiers = self.get_unique_identifiers_flags(projects=project_names)
            existing = defaultdict(dict, self.get_all_ids(
                dict(project__in=project_names), include=COMPONENTS, timeout=timeout
            ))

        # prepare contributions
        contribs = defaultdict(list)
        digests = {project_name: defaultdict(set) for project_name in project_names}
        fields = [
            comp
            for comp in self.get_model("ContributionsSchema")._properties.keys()
            if comp not in COMPONENTS
        ]
        fields.remove("needs_build")  # internal field

        for contrib in tqdm(contributions, desc="Prepare"):
            if "data" in contrib:
                serializable, error = self._is_serializable_dict(contrib["data"])
                if not serializable:
                    raise ValueError(error)

            update = "id" in contrib
            project_name = id2project[contrib["id"]] if update else contrib["project"]
            if (
                not update and unique_identifiers.get(project_name)
                and contrib["identifier"] in existing.get(project_name, {}).get("identifiers", {})
            ):
                continue

            contribs[project_name].append({
                k: deepcopy(contrib[k])
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
                        digest in existing.get(project_name, {}).get(component, {}).get("md5s", [])
                    )

                    if not ignore_dupes and dupe:
                        # TODO add matching duplicate info to msg
                        msg = f"Duplicate in {project_name}: {contrib['identifier']} {dct['name']}"
                        raise ValueError(msg)

                    digests[project_name][component].add(digest)
                    contribs[project_name][-1][component].append(dct)

                valid, error = self._is_valid_payload("Contribution", contribs[project_name][-1])
                if not valid:
                    return {"error": f"{contrib['identifier']} invalid: {error}!"}

        # submit contributions
        if contribs:
            total, total_processed = 0, 0

            def post_future(track_id, payload):
                future = self.session.post(
                    f"{self.url}/contributions/",
                    headers=self.headers,
                    data=payload,
                )
                setattr(future, "track_id", track_id)
                return future

            def put_future(pk, payload):
                future = self.session.put(
                    f"{self.url}/contributions/{pk}/",
                    headers=self.headers,
                    data=payload,
                )
                setattr(future, "track_id", pk)
                return future

            for project_name in project_names:
                ncontribs = len(contribs[project_name])
                total += ncontribs
                retries = 0

                while contribs[project_name]:
                    futures = []
                    for idx, chunk in enumerate(grouper(per_page, contribs[project_name])):
                        post_chunk = []
                        for c in chunk:
                            if "id" in c:
                                pk = c.pop("id")
                                if not c:
                                    logger.error(
                                        f"SKIPPED update of {project_name}/{pk}: empty."
                                    )

                                payload = ujson.dumps(c).encode("utf-8")
                                if len(payload) < MAX_PAYLOAD:
                                    futures.append(put_future(pk, payload))
                                else:
                                    logger.error(
                                        f"SKIPPED update of {project_name}/{pk}: too large."
                                    )
                            else:
                                post_chunk.append(c)

                        if post_chunk:
                            payload = ujson.dumps(post_chunk).encode("utf-8")
                            if len(payload) < MAX_PAYLOAD:
                                futures.append(post_future(idx, payload))
                            else:
                                logger.error(
                                    f"SKIPPED {project_name}/{idx}: too large, reduce per_request"
                                )

                    if not futures:
                        break  # nothing to do

                    responses = _run_futures(
                        futures, total=ncontribs, timeout=timeout, desc="Submit"
                    )
                    processed = sum(r.get("count", 0) for r in responses.values())
                    total_processed += processed

                    if processed != ncontribs and retry and retries < RETRIES and \
                            unique_identifiers.get(project_name):
                        existing[project_name] = self.get_all_ids(
                            dict(project=project_name), include=COMPONENTS, timeout=timeout
                        ).get(project_name, {"identifiers": set()})
                        unique_identifiers[project_name] = self.projects.getProjectByName(
                            pk=project_name, _fields=["unique_identifiers"]
                        ).result()["unique_identifiers"]
                        existing_ids = existing.get(project_name, {}).get("identifiers", [])
                        contribs[project_name] = [
                            c for c in contribs[project_name]
                            if c["identifier"] not in existing_ids
                        ]
                        retries += 1
                    else:
                        contribs[project_name] = []  # abort retrying
                        if processed != ncontribs and retry:
                            if retries >= RETRIES:
                                logger.error(f"{project_name}: Tried {RETRIES} times - abort.")
                            elif not unique_identifiers.get(project_name):
                                logger.info(
                                    f"{project_name}: resubmit failed contributions manually"
                                )

            toc = time.perf_counter()
            dt = (toc - tic) / 60
            self.init_columns()
            self._reinit()
            logger.info(f"It took {dt:.1f}min to submit {total_processed}/{total} contributions.")
        else:
            logger.info("Nothing to submit.")

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
            logger.error(f"`include` must be subset of {COMPONENTS}!")
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
                logger.info(
                    f"Downloaded {len(cids)} contributions for '{name}' in {npaths} file(s)."
                )
            else:
                logger.info(f"No new contributions to download for '{name}'.")

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
                    logger.info(
                        f"Downloaded {len(ids)} {component} for '{name}' in {npaths} file(s)."
                    )
                else:
                    logger.info(f"No new {component} to download for '{name}'.")

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
            logger.error(f"`resource` must be one of {resources}!")
            return

        formats = {"json", "csv"}
        if fmt not in formats:
            logger.error(f"`fmt` must be one of {formats}!")
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
                path.write_bytes(resp["result"])
                paths.append(path)

        return paths
