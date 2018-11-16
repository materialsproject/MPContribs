from flask_restplus import fields, Model

class NoEmailString(fields.Raw):
    def format(self, value):
        return ' '.join(value.split()[:2])

contribution_model = Model('ContributionModel', {
    '_id': fields.String(
        readOnly=True, required=True,
        description='unique contribution identifier (bson.ObjectId)',
        example='5a862206d4f1443a18fab255'
    ),
    'identifier': fields.String(
        required=True, example='mp-2715',
        description='material/composition identifier',
    ),
    'project': fields.String(
        required=True, example='dtu', readOnly=True,
        description='project slug',
    ),
    'collaborators': fields.List(
        NoEmailString(example='Patrick Huck <phuck@lbl.gov>'),
        required=True, description='list of collaborators (emails stripped)'
    ),
    #'content': fields.Nested( # TODO from project schema (see above)
    #    content, required=True,
    #    description='free-form content of the contribution'
    #)
}, mask='{_id,identifier,collaborators}')

