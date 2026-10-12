# -*- coding: utf-8 -*-
"""Flask App for MPContribs API"""
import os
import smtplib
import logging
import requests
import flask_mongorest.operators as ops

from email.message import EmailMessage
from importlib import import_module
from importlib.metadata import version
from websocket import create_connection
from flask import Flask, current_app, request, jsonify
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_mongorest import register_class
from flask_sse import sse
from flask_compress import Compress
from flasgger.base import Swagger

from mongoengine import ValidationError
from mongoengine.base.datastructures import BaseDict
from itsdangerous import URLSafeTimedSerializer
from string import punctuation, whitespace
from boltons.iterutils import remap, default_enter
from notebook.utils import url_path_join
from notebook.gateway.managers import GatewayClient
from requests.exceptions import ConnectionError, Timeout

try:
    __version__ = version("mpcontribs-api")
except Exception:
    # package is not installed
    pass

delimiter, max_depth = ".", 7  # = MAX_NESTING + 2 from client
invalidChars = set(punctuation.replace("*", "").replace("|", "") + whitespace)
is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "")
SMTP_HOST, SMTP_PORT = os.environ.get("SMTP_SERVER", "localhost:587").split(":")

# NOTE not including Size below (special for arrays)
FILTERS = {
    "LONG_STRINGS": [
        ops.Contains,
        ops.IContains,
        ops.Startswith,
        ops.IStartswith,
        ops.Endswith,
        ops.IEndswith,
    ],
    "NUMBERS": [ops.Lt, ops.Lte, ops.Gt, ops.Gte, ops.Range],
    "DATES": [ops.Before, ops.After],
    "OTHERS": [ops.Boolean, ops.Exists],
}
FILTERS["STRINGS"] = [ops.In, ops.Exact, ops.IExact, ops.Ne] + FILTERS["LONG_STRINGS"]
FILTERS["ALL"] = (
    FILTERS["STRINGS"] + FILTERS["NUMBERS"] + FILTERS["DATES"] + FILTERS["OTHERS"]
)


def get_logger(name):
    """Logger for `name`.

    Formatting, levels and the per-request/process fields (`process.name`,
    `usr.id`, ...) come from the structured logging config (`mp_logging`,
    applied in `configure_logging` and gunicorn.conf.py), so this is a plain
    `logging.getLogger`. Kept for existing imports.
    """
    return logging.getLogger(name)


def flask_debug():
    """FLASK_DEBUG as a bool (supervisord sets it to "True" / "False")."""
    return os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")


def configure_logging():
    """Structured (Datadog JSON) logging for this process, see `mp_logging`.

    `mp_logging` is a top-level module next to the app (not part of the
    `mpcontribs.api` package). If it isn't importable (e.g. the package is
    used outside the service image), the process' existing config is kept.
    """
    try:
        from mp_logging import configure_logging as _configure
    except ImportError:
        return None
    return _configure(
        # rq.worker: job start/finish messages (`flask rq worker`)
        app_loggers=("mpcontribs", "__main__", "rq.worker"),
        debug=flask_debug(),
    )


logger = get_logger(__name__)


def enter(path, key, value):
    if isinstance(value, BaseDict):
        return dict(), value.items()
    elif isinstance(value, list):
        dot_path = delimiter.join(list(path) + [key])
        raise ValidationError(f"lists not allowed ({dot_path})!")

    return default_enter(path, key, value)


def valid_key(key):
    if not key.isascii():
        raise ValidationError(f"non-ascii character(s) in {key}")

    for char in key:
        if char in invalidChars:
            raise ValidationError(f"invalid character {char} in {key}")

    if key.count("|") > 1:
        raise ValidationError(f"Only one `|` allowed in {key}. Consider nesting.")


def visit(path, key, value):
    key = key.strip()

    if len(path) + 1 > max_depth:
        dot_path = delimiter.join(list(path) + [key])
        raise ValidationError(f"max nesting ({max_depth}) exceeded for {dot_path}")

    valid_key(key)
    return key, value


def valid_dict(dct):
    remap(dct, visit=visit, enter=enter)


def send_email(to, subject, html):
    msg = EmailMessage()
    msg.set_content(html)
    msg["Subject"] = subject
    msg["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
    msg["To"] = to

    # NOTE boto3 SES client can't connect to VPC endpoint yet
    with smtplib.SMTP(host=SMTP_HOST, port=int(SMTP_PORT)) as ses_client:
        ses_client.starttls()
        ses_client.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        ses_client.send_message(msg)
        logger.warning("Email sent", extra={"email.subject": subject, "email.to": to})


def get_collections(db):
    """get list of collections in DB"""
    conn = db.app.extensions["mongoengine"][db]["conn"]
    dbname = db.app.config.get("MPCONTRIBS_DB")
    return conn[dbname].list_collection_names()


def get_resource_as_string(name, charset="utf-8"):
    """http://flask.pocoo.org/snippets/77/"""
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)


def get_kernel_endpoint(kernel_id=None, ws=False):
    gw_client = GatewayClient.instance()
    base_url = gw_client.ws_url if ws else gw_client.url

    if not base_url:
        raise ConnectionError("base URL for Kernel Gateway not set")

    base_endpoint = url_path_join(base_url, gw_client.kernels_endpoint)

    if isinstance(kernel_id, str) and kernel_id:
        return url_path_join(base_endpoint, kernel_id)

    return base_endpoint


def create_kernel_connection(kernel_id):
    url = get_kernel_endpoint(kernel_id, ws=True) + "/channels"
    return create_connection(url, skip_utf8_validation=True)


def get_kernels():
    """retrieve list of kernels from KernelGateway service"""
    try:
        r = requests.get(get_kernel_endpoint(), timeout=2)
    except (ConnectionError, Timeout):
        logger.warning("Kernel Gateway not available")
        return None

    response = r.json()
    nkernels = 3  # reserve 3 kernels for each deployment
    idx = int(os.environ.get("DEPLOYMENT", 1))

    if len(response) < nkernels * (idx + 1):
        logger.error(
            "Not enough kernels available",
            extra={
                "kernels.available": len(response),
                "kernels.required": nkernels * (idx + 1),
            },
        )
        return None

    return {kernel["id"]: None for kernel in response[idx : idx + 3]}


def get_consumer():
    groups = request.headers.get("X-Authenticated-Groups", "").split(",")
    groups += request.headers.get("X-Consumer-Groups", "").split(",")
    return {
        "username": request.headers.get("X-Consumer-Username"),
        "apikey": request.headers.get("X-Consumer-Custom-Id"),
        "groups": ",".join(set(groups)),
    }


def create_app():
    """create flask app"""
    configure_logging()
    app = Flask(__name__)
    app.config.from_pyfile("config.py", silent=True)
    app.config["USTS"] = URLSafeTimedSerializer(app.secret_key)
    app.jinja_env.globals["get_resource_as_string"] = get_resource_as_string
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True
    app.json.sort_keys = False
    MPCONTRIBS_API_HOST = app.config.get("MPCONTRIBS_API_HOST")
    app.config["TEMPLATE"]["schemes"] = ["http"] if app.debug else ["https"]
    logger.info("Using database", extra={"db.name": app.config["MPCONTRIBS_DB"]})
    Compress(app)
    Marshmallow(app)
    MongoEngine(app)
    Swagger(app, template=app.config.get("TEMPLATE"))
    setattr(app, "kernels", get_kernels())

    # NOTE: hard-code to avoid pre-generating for new deployment
    # collections = get_collections(db)
    collections = [
        "projects",
        "contributions",
        "tables",
        "attachments",
        "structures",
        "notebooks",
    ]

    for collection in collections:
        module_path = ".".join(["mpcontribs", "api", collection, "views"])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError:
            logger.exception("API module not found", extra={"module": module_path})
            continue

        try:
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix="/" + collection)
            klass = getattr(module, collection.capitalize() + "View")
            register_class(app, klass, name=collection)
            logger.info("Collection registered", extra={"collection": collection})
        except AttributeError:
            logger.exception(
                "Failed to register collection",
                extra={"module": module_path, "collection": collection},
            )

    if getattr(app, "kernels", None):
        from mpcontribs.api.notebooks.views import rq

        rq.init_app(app)

    def healthcheck():
        return jsonify({"version": app.config["VERSION"]})

    if is_gunicorn and MPCONTRIBS_API_HOST:
        app.register_blueprint(sse, url_prefix="/stream")
        app.add_url_rule("/healthcheck", view_func=healthcheck)

    try:
        from mp_logging import flask_ext
    except ImportError:
        pass
    else:
        flask_ext.init_app(app)

    @app.after_request
    def add_header(response):
        response.headers["X-Consumer-Id"] = request.headers.get("X-Consumer-Id")
        return response

    logger.info("App created")
    return app
