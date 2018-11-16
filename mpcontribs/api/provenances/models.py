from flask_restplus import fields, Model

wild = fields.Wildcard(fields.Url)
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
