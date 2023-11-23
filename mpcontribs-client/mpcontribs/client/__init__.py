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

from inspect import getfullargspec
from math import isclose
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
from concurrent.futures import as_completed
from requests_futures.sessions import FuturesSession
from urllib3.util.retry import Retry
from filetype.types.archive import Gz
from filetype.types.image import Jpeg, Png, Gif, Tiff
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from pint.errors import DimensionalityError
from tempfile import gettempdir
from plotly.express._chart_types import line as line_chart

RETRIES = 3
MAX_WORKERS = 3
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
_ipython = sys.modules['IPython'].get_ipython()


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


class MPContribsClientError(ValueError):
    """custom error for mpcontribs-client"""


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


def _compress(data):
    data_json = ujson.dumps(data, indent=4).encode("utf-8")
    content = gzip.compress(data_json)
    return len(content), content


def get_session(session=None):
    adapter_kwargs = dict(max_retries=Retry(
        total=RETRIES,
        read=RETRIES,
        connect=RETRIES,
        respect_retry_after_header=True,
        status_forcelist=[429, 502],  # rate limit
        allowed_methods={'DELETE', 'GET', 'PUT', 'POST'},
        backoff_factor=2
    ))
    return FuturesSession(
        session=session if session else _session,
        max_workers=MAX_WORKERS, adapter_kwargs=adapter_kwargs
    )


def _response_hook(resp, *args, **kwargs):
    content_type = resp.headers['content-type']
    if content_type == "application/json":
        result = resp.json()

        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], list):
                resp.result = result
                resp.count = len(result["data"])
            elif "count" in result and isinstance(result["count"], int):
                resp.count = result["count"]

            if "warning" in result:
                logger.warning(result["warning"])
            elif "error" in result and isinstance(result["error"], str):
                logger.error(result["error"][:10000] + "...")
        elif isinstance(result, list):
            resp.result = result
            resp.count = len(result)

    elif content_type == "application/gzip":
        resp.result = resp.content
        resp.count = 1
    else:
        logger.error(f"request failed with status {resp.status_code}!")
        resp.count = 0


def _chunk_by_size(items, max_size=0.95*MAX_BYTES):
    buffer, buffer_size = [], 0

    for idx, item in enumerate(items):
        item_size = _compress(item)[0]

        if buffer_size + item_size <= max_size:
            buffer.append(item)
            buffer_size += item_size
        else:
            yield buffer
            buffer = [item]
            buffer_size = item_size

    if buffer_size > 0:
        yield buffer


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return True


def _in_ipython():
    return _ipython is not None and 'IPKernelApp' in _ipython.config


if _in_ipython():
    def _hide_traceback(
        exc_tuple=None, filename=None, tb_offset=None,
        exception_only=False, running_compiled_code=False
    ):
        etype, value, tb = sys.exc_info()

        if issubclass(etype, (MPContribsClientError, SwaggerValidationError, ValidationError)):
            return _ipython._showtraceback(
                etype, value, _ipython.InteractiveTB.get_exception_only(etype, value)
            )

        return _ipython._showtraceback(
            etype, value, _ipython.InteractiveTB(etype, value, tb)
        )

    _ipython.showtraceback = _hide_traceback


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
                allowed_kwargs = getfullargspec(line_chart).args
                attrs = {k: v for k, v in self.attrs.items() if k in allowed_kwargs}
                return self.plot(**attrs)
            except Exception as e:
                logger.error(f"Can't display table: {e}")

        return self

    def info(self) -> Type[Dict]:
        """Show summary info for table"""
        info = Dict((k, v) for k, v in self.attrs.items())
        info["columns"] = ", ".join(self.columns)
        info["nrows"] = len(self.index)
        return info

    @classmethod
    def from_dict(cls, dct: dict):
        """Construct Table from dict

        Args:
            dct (dict): dictionary format of table
        """
        df = pd.DataFrame.from_records(
            dct["data"], columns=dct["columns"], index=dct["index"]
        ).apply(pd.to_numeric, errors="ignore")
        df.index = pd.to_numeric(df.index, errors="ignore")
        labels = dct["attrs"].get("labels", {})

        if "index" in labels:
            df.index.name = labels["index"]
        if "variable" in labels:
            df.columns.name = labels["variable"]

        ret = cls(df)
        ret.attrs = {k: v for k, v in dct["attrs"].items()}
        return ret

    def _clean(self):
        """clean the dataframe"""
        self.fillna('', inplace=True)
        self.index = self.index.astype(str)
        for col in self.columns:
            self[col] = self[col].astype(str)

    def _attrs_as_dict(self):
        name = self.attrs.get("name", "table")
        title = self.attrs.get("title", name)
        labels = self.attrs.get("labels", {})
        index = self.index.name
        variable = self.columns.name

        if index and "index" not in labels:
            labels["index"] = index
        if variable and "variable" not in labels:
            labels["variable"] = variable

        return name, {"title": title, "labels": labels}

    def as_dict(self):
        """Convert Table to plain dictionary"""
        self._clean()
        dct = self.to_dict(orient="split")
        dct["name"], dct["attrs"] = self._attrs_as_dict()
        return dct


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

    @classmethod
    def from_dict(cls, dct: dict):
        """Construct Structure from dict

        Args:
            dct (dict): dictionary format of structure
        """
        ret = super().from_dict(dct)
        ret.attrs = {field: dct[field] for field in ["id", "name", "md5"]}
        return ret


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
    def from_data(cls, data: Union[list, dict], name: str = "attachment"):
        """Construct attachment from data dict or list

        Args:
            data (list,dict): JSON-serializable data to go into the attachment
            name (str): name for the attachment
        """
        filename = name + ".json.gz"
        size, content = _compress(data)

        if size > MAX_BYTES:
            raise MPContribsClientError(f"{name} too large ({size} > {MAX_BYTES})!")

        return cls(
            name=filename,
            mime="application/gzip",
            content=b64encode(content).decode("utf-8")
        )

    @classmethod
    def from_file(cls, path: Union[Path, str]):
        """Construct attachment from file

        Args:
            path (pathlib.Path, str): file path
        """
        try:
            path = Path(path)
        except TypeError:
            typ = type(path)
            raise MPContribsClientError(f"use pathlib.Path or str (is: {typ}).")

        kind = guess(str(path))
        supported = isinstance(kind, SUPPORTED_FILETYPES)
        content = path.read_bytes()

        if not supported:  # try to gzip text file
            try:
                content = gzip.compress(content)
            except Exception:
                raise MPContribsClientError(
                    f"{path} is not text file or {SUPPORTED_MIMES}."
                )

        size = len(content)

        if size > MAX_BYTES:
            raise MPContribsClientError(f"{path} too large ({size} > {MAX_BYTES})!")

        return cls(
            name=path.name,
            mime=kind.mime if supported else "application/gzip",
            content=b64encode(content).decode("utf-8")
        )

    @classmethod
    def from_dict(cls, dct: dict):
        """Construct Attachment from dict

        Args:
            dct (dict): dictionary format of attachment
        """
        keys = {"id", "name", "md5", "content", "mime"}
        return cls((k, v) for k, v in dct.items() if k in keys)


class Attachments(list):
    """Wrapper class to handle attachments automatically"""
    # TODO implement "plural" versions for Attachment methods

    @classmethod
    def from_list(cls, elements: list):
        if not isinstance(elements, list):
            raise MPContribsClientError("use list to init Attachments")

        attachments = []

        for element in elements:
            if len(attachments) >= MAX_ELEMS:
                raise MPContribsClientError(f"max {MAX_ELEMS} attachments reached")

            if isinstance(element, Attachment):
                # simply append, size check already performed
                attachments.append(element)
            elif isinstance(element, (list, dict)):
                attachments += cls.from_data(element)
            elif isinstance(element, (str, Path)):
                # don't split files, user should use from_data to split
                attm = Attachment.from_file(element)
                attachments.append(attm)
            else:
                raise MPContribsClientError("invalid element for Attachments")

        return attachments

    @classmethod
    def from_data(cls, data: Union[list, dict], prefix: str = "attachment"):
        """Construct list of attachments from data dict or list

        Args:
            data (list,dict): JSON-serializable data to go into the attachments
            prefix (str): prefix for attachment name(s)
        """
        try:
            # try to make single attachment first
            return [Attachment.from_data(data, name=prefix)]
        except MPContribsClientError:
            # chunk data into multiple attachments with < MAX_BYTES
            if isinstance(data, dict):
                raise NotImplementedError("dicts not supported yet")

            attachments = []

            for idx, chunk in enumerate(_chunk_by_size(data)):
                if len(attachments) > MAX_ELEMS:
                    raise MPContribsClientError("list too large to split")

                attm = Attachment.from_data(chunk, name=f"{prefix}{idx}")
                attachments.append(attm)

            return attachments


classes_map = {"structures": Structure, "tables": Table, "attachments": Attachment}


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

                if timed_out:
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
        raise MPContribsClientError(f"Couldn't load specs from {url} for {version}!")  # not cached

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
    http_client.session.close()

    if not spec_dict["paths"]:
        return swagger_spec

    # expand regex-based query parameters for `data` columns
    query = {"name": project} if project else {}
    query["_fields"] = ["columns"]
    kwargs = dict(headers=headers, params=query)
    resp = requests.get(f"{url}/projects/", **kwargs).json()

    if not resp or not resp["data"]:
        raise MPContribsClientError(f"Failed to load projects for query {query}!")

    if project and not resp["data"]:
        raise MPContribsClientError(f"{project} doesn't exist, or access denied!")

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
                r = requests.get(f"{url}/healthcheck", timeout=5)
                if r.status_code in {200, 403}:
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

        if apikey and headers:
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
            raise MPContribsClientError(f"{self.url} not a valid URL (one of {VALID_URLS})")

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
        attr = f"{op}{resource.capitalize()}"
        resource = self.swagger_spec.resources[resource]
        param_spec = getattr(resource, attr).params["per_page"].param_spec
        return param_spec["default"], param_spec["maximum"]

    def _get_per_page(
        self, per_page: int = -1, op: str = "query", resource: str = "contributions"
    ) -> int:
        per_page_default, per_page_max = self._get_per_page_default_max(op=op, resource=resource)
        if per_page < 0:
            per_page = per_page_default
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
        nr_params_to_split = sum(
            len(v) > per_page for v in query.values() if isinstance(v, list)
        )
        if nr_params_to_split > 1:
            raise MPContribsClientError(
                f"More than one list in query with length > {per_page} not supported!"
            )

        queries = []

        for k, v in query.items():
            if isinstance(v, list):
                line_len = len(",".join(v).encode("utf-8"))

                while line_len > 3800:
                    per_page = int(0.9 * per_page)
                    vv = v[:per_page]
                    line_len = len(",".join(vv).encode("utf-8"))

                if len(v) > per_page:
                    for chunk in grouper(per_page, v):
                        queries.append({k: list(chunk)})

        query["per_page"] = per_page

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
        attr = f"{op}{rname.capitalize()}"
        method = getattr(resource, attr).http_method
        kwargs = dict(
            headers=self.headers, params=params, hooks={'response': _response_hook}
        )

        if method == "put" and data:
            kwargs["data"] = ujson.dumps(data).encode("utf-8")

        future = getattr(self.session, method)(
            f"{self.url}/{rel_url}/", **kwargs
        )
        setattr(future, "track_id", track_id)
        return future

    def available_query_params(
        self,
        startswith: tuple = None,
        resource: str = "contributions"
    ) -> list:
        resources = self.swagger_spec.resources
        resource_obj = resources.get(resource)
        if not resource_obj:
            available_resources = list(resources.keys())
            raise MPContribsClientError(f"Choose one of {available_resources}!")

        op_key = f"query{resource.capitalize()}"
        operation = resource_obj.operations[op_key]
        params = [param.name for param in operation.params.values()]
        if not startswith:
            return params

        return [
            param for param in params
            if param.startswith(startswith)
        ]

    def get_project(self, name: str = None, fields: list = None) -> Type[Dict]:
        """Retrieve a project entry

        Args:
            name (str): name of the project
            fields (list): list of fields to include in response
        """
        name = self.project or name
        if not name:
            raise MPContribsClientError("initialize client with project or set `name` argument!")

        fields = fields or ["_all"]  # retrieve all fields by default
        return Dict(self.projects.getProjectByName(pk=name, _fields=fields).result())

    def query_projects(
        self,
        query: dict = None,
        term: str = None,
        fields: list = None,
        sort: str = None,
        timeout: int = -1
    ) -> List[dict]:
        """Query projects by query and/or term (Atlas Search)

        See `client.available_query_params(resource="projects")` for keyword arguments used in
        query. Provide `term` to search for a term across all text fields in the project infos.

        Args:
            query (dict): optional query to select projects
            term (str): optional term to search text fields in projects
            fields (list): list of fields to include in response
            sort (str): field to sort by; prepend +/- for asc/desc order
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)

        Returns:
            List of projects
        """
        query = query or {}

        if self.project or "name" in query:
            return [self.get_project(name=query.get("name"), fields=fields)]

        if term:
            def search_future(search_term):
                future = self.session.get(
                    f"{self.url}/projects/search",
                    headers=self.headers,
                    hooks={'response': _response_hook},
                    params={"term": search_term},
                )
                setattr(future, "track_id", "search")
                return future

            responses = _run_futures([search_future(term)], timeout=timeout, disable=True)
            query["name__in"] = responses["search"].get("result", [])

        if fields:
            query["_fields"] = fields
        if sort:
            query["_sort"] = sort

        ret = self.projects.queryProjects(**query).result()  # first page
        total_count, total_pages = ret["total_count"], ret["total_pages"]

        if total_pages < 2:
            return ret["data"]

        for field in ["name__in", "_fields"]:
            if field in query:
                query[field] = ",".join(query[field])

        queries = []

        for page in range(2, total_pages+1):
            queries.append(deepcopy(query))
            queries[-1]["page"] = page

        futures = [self._get_future(i, q, rel_url="projects") for i, q in enumerate(queries)]
        responses = _run_futures(futures, total=total_count, timeout=timeout)

        for resp in responses.values():
            ret["data"] += resp["result"]["data"]

        return ret["data"]

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
                raise MPContribsClientError(f"Project with {query} already exists!")

        project = {
            "name": name, "title": title, "authors": authors, "description": description,
            "references": [{"label": "REF", "url": url}]
        }
        resp = self.projects.createProject(project=project).result()
        owner = resp.get("owner")
        if owner:
            logger.info(f"Project `{name}` created with owner `{owner}`")
        elif "error" in resp:
            raise MPContribsClientError(resp["error"])
        else:
            raise MPContribsClientError(resp)

    def update_project(self, update: dict, name: str = None):
        """Update project info

        Args:
            update (dict): dictionary containing project info to update
            name (str): name of the project
        """
        if not update:
            logger.warning("nothing to update")
            return

        name = self.project or name
        if not name:
            raise MPContribsClientError("initialize client with project or set `name` argument!")

        disallowed = ["is_approved", "stats", "columns", "is_public", "owner"]
        for k in list(update.keys()):
            if k in disallowed:
                logger.warning(f"removing `{k}` from update - not allowed.")
                update.pop(k)
                if k == "columns":
                    logger.info("use `client.init_columns()` to update project columns.")
                elif k == "is_public":
                    logger.info("use `client.make_public/private()` to set `is_public`.")
            elif not isinstance(update[k], bool) and not update[k]:
                logger.warning(f"removing `{k}` from update - no update requested.")
                update.pop(k)

        if not update:
            logger.warning("nothing to update")
            return

        fields = list(self.get_model("ProjectsSchema")._properties.keys())
        for k in disallowed:
            fields.remove(k)

        fields.append("stats.contributions")
        project = self.get_project(name=name, fields=fields)

        # allow name update only if no contributions in project
        if "name" in update and project["stats"]["contributions"] > 0:
            logger.warning("removing `name` from update - not allowed.")
            update.pop("name")
            logger.error("cannot change project name after contributions submitted.")

        payload = {
            k: v for k, v in update.items()
            if k in fields and project.get(k, None) != v
        }
        if not payload:
            logger.warning("nothing to update")
            return

        valid, error = self._is_valid_payload("Project", payload)
        if valid:
            resp = self.projects.updateProjectByName(pk=name, project=payload).result()
            if not resp.get("count", 0):
                raise MPContribsClientError(resp)
        else:
            raise MPContribsClientError(error)

    def delete_project(self, name: str = None):
        """Delete a project

        Args:
            name (str): name of the project
        """
        name = self.project or name
        if not name:
            raise MPContribsClientError("initialize client with project or set `name` argument!")

        if not self.get_totals(query={"name": name}, resource="projects")[0]:
            raise MPContribsClientError(f"Project `{name}` doesn't exist!")

        resp = self.projects.deleteProjectByName(pk=name).result()
        if resp and "error" in resp:
            raise MPContribsClientError(resp["error"])

    def get_contribution(self, cid: str, fields: list = None) -> Type[Dict]:
        """Retrieve a contribution

        Args:
            cid (str): contribution ObjectID
            fields (list): list of fields to include in response
        """
        if not fields:
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
            raise MPContribsClientError(f"'{tid_or_md5}' is not a valid table id or md5 hash!")

        if str_len == 32:
            tables = self.tables.queryTables(md5=tid_or_md5, _fields=["id"]).result()
            if not tables:
                raise MPContribsClientError(f"table for md5 '{tid_or_md5}' not found!")
            tid = tables["data"][0]["id"]
        else:
            tid = tid_or_md5

        op = self.swagger_spec.resources["tables"].queryTables
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

        return Table.from_dict(table)

    def get_structure(self, sid_or_md5: str) -> Type[Structure]:
        """Retrieve pymatgen structure

        Args:
            sid_or_md5 (str): ObjectId or MD5 hash digest for structure
        """
        str_len = len(sid_or_md5)
        if str_len not in {24, 32}:
            raise MPContribsClientError(f"'{sid_or_md5}' is not a valid structure id or md5 hash!")

        if str_len == 32:
            structures = self.structures.queryStructures(md5=sid_or_md5, _fields=["id"]).result()
            if not structures:
                raise MPContribsClientError(f"structure for md5 '{sid_or_md5}' not found!")
            sid = structures["data"][0]["id"]
        else:
            sid = sid_or_md5

        fields = list(self.get_model("StructuresSchema")._properties.keys())
        resp = self.structures.getStructureById(pk=sid, _fields=fields).result()
        return Structure.from_dict(resp)

    def get_attachment(self, aid_or_md5: str) -> Type[Attachment]:
        """Retrieve an attachment

        Args:
            aid_or_md5 (str): ObjectId or MD5 hash digest for attachment
        """
        str_len = len(aid_or_md5)
        if str_len not in {24, 32}:
            raise MPContribsClientError(f"'{aid_or_md5}' is not a valid attachment id or md5 hash!")

        if str_len == 32:
            attachments = self.attachments.queryAttachments(
                md5=aid_or_md5, _fields=["id"]
            ).result()
            if not attachments:
                raise MPContribsClientError(f"attachment for md5 '{aid_or_md5}' not found!")
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
            raise MPContribsClientError("initialize client with project argument!")

        columns = flatten(columns or {}, reducer="dot")

        if len(columns) > MAX_COLUMNS:
            raise MPContribsClientError(f"Number of columns larger than {MAX_COLUMNS}!")

        if not all(isinstance(v, str) for v in columns.values() if v is not None):
            raise MPContribsClientError("All values in `columns` need to be None or of type str!")

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
                    raise MPContribsClientError(f"Nesting depth larger than {MAX_NESTING} for {k}!")

                for col in scanned_columns:
                    if nesting and col.startswith(k):
                        raise MPContribsClientError(f"Duplicate definition of {k} in {col}!")

                    for n in range(1, nesting+1):
                        if k.rsplit(".", n)[0] == col:
                            raise MPContribsClientError(
                                f"Ancestor of {k} already defined in {col}!"
                            )

                is_valid_string = isinstance(v, str) and v.lower() != "nan"
                if not is_valid_string and v is not None:
                    raise MPContribsClientError(
                        f"Unit '{v}' for {k} invalid (use `None` or a non-NaN string)!"
                    )

                if v != "" and v is not None and v not in ureg:
                    raise MPContribsClientError(f"Unit '{v}' for {k} invalid!")

                scanned_columns.add(k)

            # sort to avoid "overlapping columns" error in handsontable's NestedHeaders
            sorted_columns = flatten(unflatten(columns, splitter="dot"), reducer="dot")
            # also sort by increasing nesting for better columns display
            sorted_columns = dict(
                sorted(sorted_columns.items(), key=lambda item: item[0].count("."))
            )

            # reconcile with existing columns
            resp = self.projects.getProjectByName(pk=self.project, _fields=["columns"]).result()
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
                            factor = ureg.convert(1, ureg.Unit(existing_unit), ureg.Unit(new_unit))
                        except DimensionalityError:
                            raise MPContribsClientError(
                                f"Can't convert {existing_unit} to {new_unit} for {path}"
                            )

                        if not isclose(factor, 1):
                            logger.info(f"Changing {existing_unit} to {new_unit} for {path} ...")
                            # TODO scale contributions to new unit
                            raise MPContribsClientError(
                                "Changing units not supported yet. Please resubmit"
                                " contributions or update accordingly."
                            )

                new_columns.append(new_column)

        payload = {"columns": new_columns}
        valid, error = self._is_valid_payload("Project", payload)
        if not valid:
            raise MPContribsClientError(error)

        return self.projects.updateProjectByName(pk=self.project, project=payload).result()

    def delete_contributions(self, query: dict = None, timeout: int = -1):
        """Remove all contributions for a query

        Args:
            query (dict): optional query to select contributions
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
        """
        if not self.project and (not query or "project" not in query):
            raise MPContribsClientError(
                "initialize client with project, or include project in query!"
            )

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
            raise MPContribsClientError(
                f"There were errors and {left} contributions are left to delete!"
            )

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
            raise MPContribsClientError(f"`op` has to be one of {ops}")

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

    def count(self, query: dict = None) -> int:
        """shortcut for get_totals()"""
        return self.get_totals(query=query)[0]

    def get_unique_identifiers_flags(self, query: dict = None) -> dict:
        """Retrieve values for `unique_identifiers` flags.

        See `client.available_query_params(resource="projects")` for available query parameters.

        Args:
            query (dict): query to select projects

        Returns:
            {"<project-name>": True|False, ...}
        """
        return {
            p["name"]: p["unique_identifiers"]
            for p in self.query_projects(query=query, fields=["name", "unique_identifiers"])
        }

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
            raise MPContribsClientError(f"`include` must be subset of {COMPONENTS}!")

        fmts = {"sets", "map"}
        if fmt not in fmts:
            raise MPContribsClientError(f"`fmt` must be subset of {fmts}!")

        ops = {"query", "create", "update", "delete", "download"}
        if op not in ops:
            raise MPContribsClientError(f"`op` has to be one of {ops}")

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

        See `client.available_query_params()` for keyword arguments used in query.

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
                raise MPContribsClientError("No contributions match the query.")

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

        See `client.available_query_params()` for keyword arguments used in query.

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
            raise MPContribsClientError(error)

        if "data" in data:
            serializable, error = self._is_serializable_dict(data["data"])
            if not serializable:
                raise MPContribsClientError(error)

        query = query or {}

        if not self.project and (not query or "project" not in query):
            raise MPContribsClientError(
                "initialize client with project, or include project in query!"
            )

        if "project" in query and self.project != query["project"]:
            raise MPContribsClientError(
                f"client initialized with different project {self.project}!"
            )

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
            raise MPContribsClientError(
                "initialize client with project, or include project in query!"
            )

        query = query or {}

        if self.project:
            query["project"] = self.project

        try:
            resp = self.projects.getProjectByName(
                pk=query["project"], _fields=["is_public", "is_approved"]
            ).result()
        except HTTPNotFound:
            raise MPContribsClientError(f"project `{query['project']}` not found or access denied!")

        if not recursive and resp["is_public"] == is_public:
            return {"warning": f"`is_public` already set to {is_public} for `{query['project']}`."}

        ret = {}

        if resp["is_public"] != is_public:
            if is_public and not resp["is_approved"]:
                raise MPContribsClientError(f"project `{query['project']}` is not approved yet!")

            resp = self.projects.updateProjectByName(
                pk=query["project"], project={"is_public": is_public}
            ).result()
            ret["published"] = resp["count"] == 1

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
            timeout (int): cancel remaining requests if timeout exceeded (in seconds)
            skip_dupe_check (bool): skip duplicate check for contribution identifiers
        """
        if not contributions or not isinstance(contributions, list):
            raise MPContribsClientError("Please provide list of contributions to submit.")

        # get existing contributions
        tic = time.perf_counter()
        project_names = set()
        collect_ids = []
        require_one_of = {"data"} | set(COMPONENTS)

        for idx, c in enumerate(contributions):
            has_keys = require_one_of & c.keys()
            if not has_keys:
                raise MPContribsClientError(f"Nothing to submit for contribution #{idx}!")
            elif not all(c[k] for k in has_keys):
                for k in has_keys:
                    if not c[k]:
                        raise MPContribsClientError(f"Empty `{k}` for contribution #{idx}!")
            elif "id" in c:
                collect_ids.append(c["id"])
            elif "project" in c and "identifier" in c:
                project_names.add(c["project"])
            elif self.project and "project" not in c and "identifier" in c:
                project_names.add(self.project)
                contributions[idx]["project"] = self.project
            else:
                raise MPContribsClientError(
                    f"Provide `project` & `identifier`, or `id` for contribution #{idx}!"
                )

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
            nproj = len(project_names)
            query = {"name__in": project_names} if nproj > 1 else {"name": project_names[0]}
            unique_identifiers = self.get_unique_identifiers_flags(query)
            query = {"project__in": project_names} if nproj > 1 else {"project": project_names[0]}
            existing = defaultdict(dict, self.get_all_ids(
                query, include=COMPONENTS, timeout=timeout
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
                contrib["data"] = unflatten(contrib["data"], splitter="dot")
                serializable, error = self._is_serializable_dict(contrib["data"])
                if not serializable:
                    raise MPContribsClientError(error)

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
                    raise MPContribsClientError(f"Too many {component} ({nelems} > {MAX_ELEMS})!")

                if update and not nelems:
                    continue  # nothing to update for this component

                contribs[project_name][-1][component] = []

                for idx, element in enumerate(elements):
                    if update and element is None:
                        contribs[project_name][-1][component].append(None)
                        continue

                    is_structure = isinstance(element, PmgStructure)
                    is_table = isinstance(element, (pd.DataFrame, Table))
                    is_attachment = isinstance(element, (str, Path, Attachment))
                    if component == "structures" and not is_structure:
                        raise MPContribsClientError(f"Use pymatgen Structure for {component}!")
                    elif component == "tables" and not is_table:
                        raise MPContribsClientError(
                            f"Use pandas DataFrame or mpontribs.client.Table for {component}!"
                        )
                    elif component == "attachments" and not is_attachment:
                        raise MPContribsClientError(
                            f"Use str, pathlib.Path or mpcontribs.client.Attachment for {component}"
                        )

                    if is_structure:
                        dct = element.as_dict()
                        del dct["@module"]
                        del dct["@class"]

                        if not dct.get("charge"):
                            del dct["charge"]

                        if "properties" in dct:
                            if dct["properties"]:
                                logger.warning("storing structure properties not supported, yet!")
                            del dct["properties"]
                    elif is_table:
                        table = element
                        if not isinstance(table, Table):
                            table = Table(element)
                            table.attrs = element.attrs

                        table._clean()
                        dct = table.to_dict(orient="split")
                    elif is_attachment:
                        if isinstance(element, (str, Path)):
                            element = Attachment.from_file(element)

                        dct = {k: element[k] for k in ["mime", "content"]}

                    digest = get_md5(dct)

                    if is_structure:
                        dct["name"] = getattr(element, "name", "structure")
                    elif is_table:
                        dct["name"], dct["attrs"] = table._attrs_as_dict()
                    elif is_attachment:
                        dct["name"] = element.name

                    dupe = bool(
                        digest in digests[project_name][component] or
                        digest in existing.get(project_name, {}).get(component, {}).get("md5s", [])
                    )

                    if not ignore_dupes and dupe:
                        # TODO add matching duplicate info to msg
                        msg = f"Duplicate in {project_name}: {contrib['identifier']} {dct['name']}"
                        raise MPContribsClientError(msg)

                    digests[project_name][component].add(digest)
                    contribs[project_name][-1][component].append(dct)

                valid, error = self._is_valid_payload("Contribution", contribs[project_name][-1])
                if not valid:
                    raise MPContribsClientError(f"{contrib['identifier']} invalid: {error}!")

        # submit contributions
        if contribs:
            total, total_processed = 0, 0
            nmax = 1000  # TODO this should be set dynamically from `bulk_update_limit`

            def post_future(track_id, payload):
                future = self.session.post(
                    f"{self.url}/contributions/",
                    headers=self.headers,
                    hooks={'response': _response_hook},
                    data=payload,
                )
                setattr(future, "track_id", track_id)
                return future

            def put_future(pk, payload):
                future = self.session.put(
                    f"{self.url}/contributions/{pk}/",
                    headers=self.headers,
                    hooks={'response': _response_hook},
                    data=payload,
                )
                setattr(future, "track_id", pk)
                return future

            for project_name in project_names:
                ncontribs = len(contribs[project_name])
                total += ncontribs
                retries = 0

                while contribs[project_name]:
                    futures, post_chunk, idx = [], [], 0

                    for n, c in enumerate(contribs[project_name]):
                        if "id" in c:
                            pk = c.pop("id")
                            if not c:
                                logger.error(f"SKIPPED: update of {project_name}/{pk} empty.")

                            payload = ujson.dumps(c).encode("utf-8")
                            if len(payload) < MAX_PAYLOAD:
                                futures.append(put_future(pk, payload))
                            else:
                                logger.error(f"SKIPPED: update of {project_name}/{pk} too large.")
                        else:
                            next_post_chunk = post_chunk + [c]
                            next_payload = ujson.dumps(next_post_chunk).encode("utf-8")
                            if len(next_post_chunk) > nmax or len(next_payload) >= MAX_PAYLOAD:
                                if post_chunk:
                                    payload = ujson.dumps(post_chunk).encode("utf-8")
                                    futures.append(post_future(idx, payload))
                                    post_chunk = []
                                    idx += 1
                                else:
                                    logger.error(f"SKIPPED: contrib {project_name}/{n} too large.")
                                    continue

                            post_chunk.append(c)

                    if post_chunk and len(futures) < ncontribs:
                        payload = ujson.dumps(post_chunk).encode("utf-8")
                        futures.append(post_future(idx, payload))

                    if not futures:
                        break  # nothing to do

                    responses = _run_futures(
                        futures, total=ncontribs-total_processed, timeout=timeout, desc="Submit"
                    )
                    processed = sum(r.get("count", 0) for r in responses.values())
                    total_processed += processed

                    if total_processed != ncontribs and retries < RETRIES and \
                            unique_identifiers.get(project_name):
                        logger.info(f"{total_processed}/{ncontribs} processed -> retrying ...")
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
                        if total_processed != ncontribs:
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
            raise MPContribsClientError(f"`include` must be subset of {COMPONENTS}!")

        all_ids = self.get_all_ids(query, include=components, timeout=timeout)
        fmt = query.get("format", "json")
        contributions, components_loaded = [], defaultdict(dict)

        for name, values in all_ids.items():
            if timeout > 0:
                timeout -= time.perf_counter() - start
                if timeout < 1:
                    return contributions

                start = time.perf_counter()

            for component in components:
                if timeout > 0:
                    timeout -= time.perf_counter() - start
                    if timeout < 1:
                        return contributions

                    start = time.perf_counter()

                ids = list(values[component]["ids"])
                if not ids:
                    continue

                paths = self._download_resource(
                    resource=component, ids=ids, fmt=fmt,
                    outdir=outdir, overwrite=overwrite, timeout=timeout
                )
                logger.debug(
                    f"Downloaded {len(ids)} {component} for '{name}' in {len(paths)} file(s)."
                )

                cls = classes_map[component]
                for path in paths:
                    with gzip.open(path, "r") as f:
                        for c in ujson.load(f):
                            components_loaded[component][c["id"]] = cls.from_dict(c)

            cids = list(values["ids"])
            if not cids:
                continue

            paths = self._download_resource(
                resource="contributions", ids=cids, fmt=fmt,
                outdir=outdir, overwrite=overwrite, timeout=timeout
            )
            logger.debug(
                f"Downloaded {len(cids)} contributions for '{name}' in {len(paths)} file(s)."
            )

            for path in paths:
                with gzip.open(path, "r") as f:
                    for c in ujson.load(f):
                        contrib = Dict(c)
                        for component in components_loaded.keys():
                            contrib[component] = [
                                components_loaded[component][d["id"]]
                                for d in contrib.pop(component)
                            ]

                        contributions.append(contrib)

        return contributions

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
            raise MPContribsClientError(f"`resource` must be one of {resources}!")

        formats = {"json", "csv"}
        if fmt not in formats:
            raise MPContribsClientError(f"`fmt` must be one of {formats}!")

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
            paths.append(path)

            if not path.exists() or overwrite:
                futures.append(self._get_future(
                    path, query, rel_url=f"{resource}/download/gz"
                ))

        if futures:
            responses = _run_futures(futures, timeout=timeout)

            for path, resp in responses.items():
                path.write_bytes(resp["result"])

        return paths
