"""Flask App for MPContribs API"""

import os
import logging
import yaml
from importlib import import_module
from flask import Flask, current_app
from flask_marshmallow import Marshmallow
from flask_mongoengine import MongoEngine
from flask_mongorest import register_class
from flask_mongorest.exceptions import ValidationError
from flask_log import Logging
from flask_mail import Mail, Message
from flasgger.base import Swagger
from pandas.io.json._normalize import nested_to_record
from typing import Any, Dict
from itsdangerous import URLSafeTimedSerializer
from pint import UnitRegistry
from fdict import fdict
from string import punctuation

ureg = UnitRegistry(auto_reduce_dimensions=True)
ureg.default_format = '~'
Q_ = ureg.Quantity
delimiter, max_depth = '.', 2
invalidChars = set(punctuation.replace('|', ''))
quantity_keys = ['display', 'value', 'unit']

for mod in ['matplotlib', 'toronado.cssutils', 'selenium.webdriver.remote.remote_connection']:
    log = logging.getLogger(mod)
    log.setLevel('INFO')

logger = logging.getLogger('app')
mail = Mail()


def validate_data(doc):
    d = fdict(doc, delimiter=delimiter)

    for key in list(d.keys()):
        nodes = key.split(delimiter)
        is_quantity_key = int(nodes[-1] in quantity_keys)

        if len(nodes) > max_depth + is_quantity_key:
            raise ValidationError({'error': f'max nesting ({max_depth}) exceeded for {key}'})

        if is_quantity_key:
            continue

        for node in nodes:
            for char in node:
                if char in invalidChars:
                    raise ValidationError({'error': f'invalid character {char} in {node} ({key})'})

        value = str(d[key])
        if ' ' in value or isinstance(d[key], (int, float)):
            try:
                q = Q_(value).to_compact()
            except Exception as ex:
                raise ValidationError({'error': str(ex)})
            d[key] = {'display': str(q), 'value': q.magnitude, 'unit': format(q.units, '~')}

    return d.to_dict_nested()


def send_email(to, subject, template):
    msg = Message(
        subject, recipients=[to], html=template,
        sender=current_app.config['MAIL_DEFAULT_SENDER']
    )
    mail.send(msg)

def get_collections(db):
    """get list of collections in DB"""
    conn = db.app.extensions['mongoengine'][db]['conn']
    dbname = db.app.config.get('MPCONTRIBS_DB')
    return conn[dbname].list_collection_names()


def get_resource_as_string(name, charset='utf-8'):
    """http://flask.pocoo.org/snippets/77/"""
    with current_app.open_resource(name) as f:
        return f.read().decode(charset)


# utility to use in views
def construct_query(filters):
    """constructs a mongoengine query from a list of filters

    example:
        C__gte:0.42,C__lte:2.10,ΔE-QP.direct__lte:11.3
        -> data__C__value__lte
    """
    query = {}
    for f in filters:
        if '__' in f and ':' in f:
            k, v = f.split(':')
            col, op = k.rsplit('__', 1)
            col = col.replace(".", "__")
            try:
                val = float(v)
                key = f'data__{col}__value__{op}'
                query[key] = val
            except ValueError:
                key = f'data__{col}__{op}'
                query[key] = v
    return query


# https://stackoverflow.com/a/55545369
def unflatten(
    d: Dict[str, Any],
    base: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Convert any keys containing dotted paths to nested dicts

    >>> unflatten({'a': 12, 'b': 13, 'c': 14})  # no expansion
    {'a': 12, 'b': 13, 'c': 14}

    >>> unflatten({'a.b.c': 12})  # dotted path expansion
    {'a': {'b': {'c': 12}}}

    >>> unflatten({'a.b.c': 12, 'a': {'b.d': 13}})  # merging
    {'a': {'b': {'c': 12, 'd': 13}}}

    >>> unflatten({'a.b': 12, 'a': {'b': 13}})  # insertion-order overwrites
    {'a': {'b': 13}}

    >>> unflatten({'a': {}})  # insertion-order overwrites
    {'a': {}}
    """
    if base is None:
        base = {}

    for key, value in d.items():
        root = base

        ###
        # If a dotted path is encountered, create nested dicts for all but
        # the last level, then change root to that last level, and key to
        # the final key in the path. This allows one final setitem at the bottom
        # of the loop.
        if '.' in key:
            *parts, key = key.split('.')

            for part in parts:
                root.setdefault(part, {})
                root = root[part]

        if isinstance(value, dict):
            value = unflatten(value, root.get(key, {}))

        root[key] = value

    return base


def get_cleaned_data(data):
    return dict(
        (k.rsplit('.', 1)[0] if k.endswith('.display') else k, v)
        for k, v in nested_to_record(data, sep='.').items()
        if not k.endswith('.value') and not k.endswith('.unit')
    )


def create_app():
    """create flask app"""
    app = Flask(__name__)
    app.config.from_pyfile('config.py', silent=True)
    app.config['USTS'] = URLSafeTimedSerializer(app.secret_key)
    app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string
    if app.config.get('DEBUG'):
        from flask_cors import CORS
        CORS(app)  # enable for development (allow localhost)


    mail.init_app(app)
    Logging(app)
    Marshmallow(app)
    db = MongoEngine(app)
    Swagger(app, template=app.config.get('TEMPLATE'))
    collections = get_collections(db)

    for collection in collections:
        module_path = '.'.join(['mpcontribs', 'api', collection, 'views'])
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as ex:
            logger.warning(f'API module {module_path}: {ex}')
            continue

        try:
            blueprint = getattr(module, collection)
            app.register_blueprint(blueprint, url_prefix='/'+collection)
            klass = getattr(module, collection.capitalize() + 'View')
            register_class(app, klass, name=collection)
        except AttributeError as ex:
            logger.warning(f'Failed to register {module_path}: {collection} {ex}')

    # TODO discover user-contributed views automatically
    collection = 'redox_thermo_csp'
    module_path = '.'.join(['mpcontribs', 'api', collection, 'views'])
    try:
        module = import_module(module_path)
        blueprint = getattr(module, collection)
        app.register_blueprint(blueprint, url_prefix='/'+collection)
    except ModuleNotFoundError as ex:
        logger.warning(f'API module {module_path}: {ex}')

    return app
