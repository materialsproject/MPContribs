from flask_restplus import fields, Model, SchemaModel

dtu_urls = SchemaModel('DtuUrls', {
    'properties': {
        "AENM": {'type': 'string', 'format': 'uri'},
        "PRA": {'type': 'string', 'format': 'uri'},
        "PRB": {'type': 'string', 'format': 'uri'},
    }
})

dtu_bandgaps = SchemaModel('DtuBandgaps', {
    'properties': {
        "direct": {'type': 'string'},
        "indirect": {'type': 'string'},
    }
})

dtu_data = SchemaModel('DtuData', {
    'properties': {
        "C": {'type': 'string'},
        "ΔE-KS": {'$ref': '#/definitions/DtuBandgaps'},
        "ΔE-QP": {'$ref': '#/definitions/DtuBandgaps'},
    }
})

content = SchemaModel('Content', {
    'required': ['title', 'description', 'authors', 'urls'],
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string'},
        'authors': {'type': 'string'},
        'urls': {'$ref': '#/definitions/DtuUrls'},
        "contributor": {'type': 'string'},
        "formula": {'type': 'string'},
        "input_url": {'type': 'string', 'format': 'uri'},
        "project": {'type': 'string'},
        "ICSD": {'type': 'string'},
        "data": {'$ref': '#/definitions/DtuData'},
    }
})

model = Model('ContributionModel', {
    '_id': fields.String(
        readOnly=True, required=True,
        description='unique contribution identifier (bson.ObjectId)',
        example='5a862206d4f1443a18fab255'
    ),
    'mp_cat_id': fields.String(
        required=True, #attribute='identifier',
        description='material/composition identifier',
        example='mp-2715'
    ),
    'project': fields.String(
        required=True, example='dtu', readOnly=True,
        description='project slug',
    ),
    'collaborators': fields.List(
        fields.String(example='Patrick Huck <phuck@lbl.gov>'),
        required=True, description='list of collaborators'
    ),
    #'content': fields.Nested(
    #    content, required=True,
    #    description='free-form content of the contribution'
    #)
}, mask='{_id,mp_cat_id,collaborators}') # TODO SchemaModel.items error for content!

