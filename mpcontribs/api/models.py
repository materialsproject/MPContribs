from flask_restplus import SchemaModel

#### PROJECT-SPECIFIC CONTENT ####

schema_models = [
    SchemaModel('DtuBandgaps', {
        'properties': {
            "direct": {'type': 'string'},
            "indirect": {'type': 'string'},
        }
    }),
    SchemaModel('DtuData', {
        'properties': {
            "C": {'type': 'string'},
            "ΔE-KS": {'$ref': '#/definitions/DtuBandgaps'},
            "ΔE-QP": {'$ref': '#/definitions/DtuBandgaps'},
        }
    })
    #"contributor": {'type': 'string'},
    #"formula": {'type': 'string'},
    #"input_url": {'type': 'string', 'format': 'uri'},
    #"ICSD": {'type': 'string'},
    #"data": {'$ref': '#/definitions/DtuData'},
]

from flask_restplus import fields, Model

wild = fields.Wildcard(fields.Url) # URL format?
urls_model = Model('Urls', {'*': wild})

provenance_model = Model('Content', {
    'title': fields.String(
        required=True, example='GLLB-SC Bandgaps',
        description='unique contribution identifier (bson.ObjectId)',
    ),
    'description': fields.String(
        required=True, description='Brief description of the project',
    ),
    'authors': fields.String(
        required=True, example='P. Huck, K. Persson',
        description='comma-separated list of authors',
    ),
    'urls': fields.Nested(
        urls, required=True,
        description='list of URLs for references'
    )
})
