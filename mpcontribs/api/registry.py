from flask_rebar import HandlerRegistry
from marshmallow_mongoengine import fields
from flask_rebar.swagger_generation.marshmallow_to_swagger import \
        response_converter_registry, StringConverter

from mpcontribs.api.config import VERSION
from mpcontribs.api.provenance import get_provenance, ProvenanceSchema

class ObjectIdConverter(StringConverter):
    MARSHMALLOW_TYPE = fields.ObjectId

registry = HandlerRegistry(prefix=VERSION)
response_converter_registry.register_type(ObjectIdConverter())

registry.add_handler(
    get_provenance, rule='/provenances/<project>', method='GET',
    marshal_schema=ProvenanceSchema(),
)
