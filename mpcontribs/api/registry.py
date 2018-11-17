from flask_rebar import HandlerRegistry
from marshmallow_mongoengine import fields
from flask_rebar.swagger_generation import SwaggerV2Generator
from flask_rebar.swagger_generation.marshmallow_to_swagger import \
        response_converter_registry, StringConverter

from mpcontribs.api.config import VERSION
from mpcontribs.api.provenance import add_all_handlers

class ObjectIdConverter(StringConverter):
    MARSHMALLOW_TYPE = fields.ObjectId

swaggen = SwaggerV2Generator(
    title='MPContribs API', version=VERSION,
    description='Operations to retrieve materials data contributed to MP'
)

registry = HandlerRegistry(prefix=VERSION, swagger_generator=swaggen)
response_converter_registry.register_type(ObjectIdConverter())
add_all_handlers(registry)
