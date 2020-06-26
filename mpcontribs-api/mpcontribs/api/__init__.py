# -*- coding: utf-8 -*-
"""Flask App for MPContribs API"""

import os
import logging
import boto3

from importlib import import_module
from flask import Flask, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_mongorest import register_class
from flask_mongorest.exceptions import ValidationError
from flask_log import Logging
from flask_sse import sse
from flask_compress import Compress
from flasgger.base import Swagger
from marshmallow.utils import get_value
from itsdangerous import URLSafeTimedSerializer
from pint import UnitRegistry
from pint.unit import UnitDefinition
from pint.converters import ScaleConverter
from fdict import fdict
from string import punctuation
from decimal import Decimal


ureg = UnitRegistry(
    preprocessors=[
        lambda s: s.replace("%%", " permille "),
        lambda s: s.replace("%", " percent "),
    ]
)
ureg.default_format = "P~"

ureg.define(UnitDefinition("percent", "%", (), ScaleConverter(0.01)))
ureg.define(UnitDefinition("permille", "%%", (), ScaleConverter(0.001)))
ureg.define(UnitDefinition("ppm", "ppm", (), ScaleConverter(1e-6)))
ureg.define(UnitDefinition("ppb", "ppb", (), ScaleConverter(1e-9)))
ureg.define("atom = 1")
ureg.define("bohr_magneton = e * hbar / (2 * m_e) = µᵇ = µ_B = mu_B")
ureg.define("electron_mass = 9.1093837015e-31 kg = mₑ = m_e")

Q_ = ureg.Quantity
delimiter, max_depth = ".", 2
max_dgts = 6
invalidChars = set(punctuation.replace("|", "").replace("*", ""))
invalidChars.add(" ")
quantity_keys = ["display", "value", "unit"]

for mod in [
    "matplotlib",
    "toronado.cssutils",
    "selenium.webdriver.remote.remote_connection",
    "botocore",
]:
    log = logging.getLogger(mod)
    log.setLevel("INFO")

logger = logging.getLogger("app")
sns_client = boto3.client("sns")


def is_float(s):
    try:
        float(s)
    except ValueError:
        return False
    return True


def validate_data(doc, sender=None, project=None):
    d = fdict(doc, delimiter=delimiter)

    for key in list(d.keys()):
        key = key.strip()
        nodes = key.split(delimiter)
        is_quantity_key = int(nodes[-1] in quantity_keys)

        if len(nodes) > max_depth + is_quantity_key:
            raise ValidationError(
                {"error": f"max nesting ({max_depth}) exceeded for {key}"}
            )

        if is_quantity_key:
            continue

        for node in nodes:
            for char in node:
                if char in invalidChars:
                    raise ValidationError(
                        {"error": f"invalid character '{char}' in {node} ({key})"}
                    )

        value = str(d[key])
        words = value.split()
        try_quantity = bool(len(words) == 2 and is_float(words[0]))
        if try_quantity or isinstance(d[key], (int, float)):
            try:
                q = Q_(value).to_compact()
                if not q.check(0):
                    q.ito_reduced_units()
                if sender:
                    _key = key.replace(".", "__")
                    query = {"project": project, f"data__{_key}__exists": True}
                    sample = (
                        sender.objects.only(f"data.{key}.unit").filter(**query).first()
                    )
                    if sample:
                        q.ito(get_value(sample["data"], f"{key}.unit"))
                v = Decimal(str(q.magnitude))
                vt = v.as_tuple()
                if vt.exponent < 0:
                    dgts = len(vt.digits)
                    dgts = max_dgts if dgts > max_dgts else dgts
                    v = f"{v:.{dgts}g}"
                    if try_quantity:
                        q = Q_(f"{v} {q.units}")
            except Exception as ex:
                raise ValidationError({"error": str(ex)})
            d[key] = {"display": str(q), "value": q.magnitude, "unit": str(q.units)}

    return d.to_dict_nested()


def send_email(to, subject, template):
    try:
        sns_client.publish(TopicArn=to, Message=template, Subject=subject)
    except Exception as ex:
        raise ValidationError({"error": str(ex)})


def get_collections(db):
    """get list of collections in DB"""
    conn = db.app.extensions["mongoengine"][db]["conn"]
    dbname = db.app.config.get("MPCONTRIBS_DB")
    return conn[dbname].list_collection_names()


def get_resource_as_string(name, charset="utf-8"):
    """http://flask.pocoo.org/snippets/77/"""
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)


def create_app():
    """create flask app"""
    app = Flask(__name__)
    app.config.from_pyfile("config.py", silent=True)
    logger.warning("database: " + app.config["MPCONTRIBS_DB"])
    app.config["USTS"] = URLSafeTimedSerializer(app.secret_key)
    app.jinja_env.globals["get_resource_as_string"] = get_resource_as_string
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True

    if app.config.get("DEBUG"):
        from flask_cors import CORS

        CORS(app)  # enable for development (allow localhost)

    Compress(app)
    Logging(app)
    Marshmallow(app)
    MongoEngine(app)
    Swagger(app, template=app.config.get("TEMPLATE"))
    # collections = get_collections(db)  # hard-code to avoid pre-generating for new deployment
    collections = [
        "projects",
        "contributions",
        "tables",
        "structures",
        "notebooks",
        "cards",
    ]

    for collection in collections:
        module_path = ".".join(["mpcontribs", "api", collection, "views"])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as ex:
            logger.warning(f"API module {module_path}: {ex}")
            continue

        try:
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix="/" + collection)
            klass = getattr(module, collection.capitalize() + "View")
            register_class(app, klass, name=collection)
            logger.warning(f"{collection} registered")
        except AttributeError as ex:
            logger.warning(f"Failed to register {module_path}: {collection} {ex}")

    # TODO discover user-contributed views automatically
    # only load for main deployment
    if os.environ.get("API_PORT", "5000") == "5000":
        collection = "redox_thermo_csp"
        module_path = ".".join(["mpcontribs", "api", collection, "views"])
        try:
            module = import_module(module_path)
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix="/" + collection)
            logger.warning(f"{collection} registered")
        except ModuleNotFoundError as ex:
            logger.warning(f"API module {module_path}: {ex}")

    app.register_blueprint(sse, url_prefix="/stream")
    # TODO add healthcheck view/url
    logger.warning("app created.")
    return app
