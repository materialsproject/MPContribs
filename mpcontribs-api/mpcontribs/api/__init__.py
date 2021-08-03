# -*- coding: utf-8 -*-
"""Flask App for MPContribs API"""
import os
import logging
import boto3
import requests
import flask_monitoringdashboard as dashboard

from importlib import import_module
from websocket import create_connection
from flask import Flask, current_app, request
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_mongorest import register_class
from flask_log import Logging
from flask_sse import sse
from flask_compress import Compress
from flasgger.base import Swagger

from mongoengine import ValidationError
from mongoengine.base.datastructures import BaseDict
from itsdangerous import URLSafeTimedSerializer
from string import punctuation
from boltons.iterutils import remap, default_enter
from notebook.utils import url_path_join
from notebook.gateway.managers import GatewayClient
from requests.exceptions import ConnectionError


delimiter, max_depth = ".", 4
invalidChars = set(punctuation.replace("*", ""))
invalidChars.add(" ")

for mod in [
    "matplotlib",
    "toronado.cssutils",
    "selenium.webdriver.remote.remote_connection",
    "botocore",
    "websockets.protocol",
    "asyncio",
]:
    log = logging.getLogger(mod)
    log.setLevel("INFO")

logger = logging.getLogger("app")
sns_client = boto3.client("sns")


def enter(path, key, value):
    if isinstance(value, BaseDict):
        return dict(), value.items()
    elif isinstance(value, list):
        dot_path = delimiter.join(list(path) + [key])
        raise ValidationError(f"lists not allowed ({dot_path})!")

    return default_enter(path, key, value)


def valid_key(key):
    for char in key:
        if char in invalidChars:
            raise ValidationError(f"invalid character {char} in {key}")


def visit(path, key, value):
    key = key.strip()

    if len(path) + 1 > max_depth:
        dot_path = delimiter.join(list(path) + [key])
        raise ValidationError(f"max nesting ({max_depth}) exceeded for {dot_path}")

    valid_key(key)
    return key, value


def valid_dict(dct):
    remap(dct, visit=visit, enter=enter)


def send_email(to, subject, template):
    sns_client.publish(TopicArn=to, Message=template, Subject=subject)


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
        r = requests.get(get_kernel_endpoint())
    except ConnectionError:
        logger.warning("Kernel Gateway NOT AVAILABLE")
        return None

    response = r.json()
    nkernels = 3  # reserve 3 kernels for each deployment
    idx = int(os.environ.get("DEPLOYMENT"))

    if len(response) < nkernels * (idx + 1):
        logger.error("NOT ENOUGH KERNELS AVAILABLE")
        return None

    return {kernel["id"]: None for kernel in response[idx:idx+3]}


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
    app = Flask(__name__)
    app.config.from_pyfile("config.py", silent=True)
    logger.info("database: " + app.config["MPCONTRIBS_DB"])
    app.config["USTS"] = URLSafeTimedSerializer(app.secret_key)
    app.jinja_env.globals["get_resource_as_string"] = get_resource_as_string
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True
    DEBUG = app.config.get("DEBUG")

    if DEBUG:
        from flask_cors import CORS

        CORS(app)  # enable for development (allow localhost)

    Compress(app)
    Logging(app)
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
        except ModuleNotFoundError as ex:
            logger.error(f"API module {module_path}: {ex}")
            continue

        try:
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix="/" + collection)
            klass = getattr(module, collection.capitalize() + "View")
            register_class(app, klass, name=collection)
            logger.info(f"{collection} registered")
        except AttributeError as ex:
            logger.error(f"Failed to register {module_path}: {collection} {ex}")

    if app.kernels:
        from mpcontribs.api.notebooks.views import rq, make
        rq.init_app(app)
        cron_job_id = app.config["CRON_JOB_ID"]
        make.cron('*/3 * * * *', cron_job_id)
        logger.info(f"cronjob {cron_job_id} added.")

    def healthcheck():
        if not DEBUG and not app.kernels:
            return "KERNEL GATEWAY NOT AVAILABLE", 500

        return "OK"

    app.register_blueprint(sse, url_prefix="/stream")
    app.add_url_rule("/healthcheck", view_func=healthcheck)

    dashboard.config.init_from(file="dashboard.cfg")
    dashboard.config.version = app.config["VERSION"]
    dashboard.config.table_prefix = app.config["MONITORING_TABLE_PREFIX"]
    db_password = os.environ["POSTGRES_DB_PASSWORD"]
    db_host = os.environ["POSTGRES_DB_HOST"]
    dashboard.config.database_name = f"postgresql://kong:{db_password}@{db_host}/kong"
    dashboard.bind(app)

    logger.info("app created.")
    return app
