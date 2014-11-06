from pymatgen.matproj.snl import Author
from pymongo import MongoClient
host, port, db_name = 'localhost', 27019, 'user_contributions'
username, password = 'test', 'test'
client = MongoClient(host, port, j=False)
client[db_name].authenticate(username, password)
contrib_coll = client[db_name].contributions
mat_coll = client[db_name].materials

# http://stackoverflow.com/a/19647596
def flatten_dict(dd, separator='_', prefix=''):
    return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_dict(vv, separator, kk).items()
           } if isinstance(dd, dict) else { prefix : dd }

# NOTE: distinguish mp cat's by format of mp_cat_id
pipeline = [
    { '$group': {
        '_id': '$mp_cat_id',
        'num_contribs': { '$sum': 1 },
        'contrib_ids': { '$addToSet': '$contribution_id' }
    }}
]
for doc in contrib_coll.aggregate(pipeline, cursor={}):
    for cid in doc['contrib_ids']:
        contrib = contrib_coll.find_one(
            {'contribution_id': cid}, {
                'content.data': 0, 'content.plots': 0, '_id': 0
            }
        )
        author = Author.parse_author(contrib['contributor_email'])
        project = str(author.name).translate(None, '.')
        tabular_data = flatten_dict(contrib)
        mat_coll.update( # TODO: overwriting previous nested keys?
            {'task_id': doc['_id']},
            { '$set': {
                'external_data': {
                    project: { 'tabular_data': tabular_data }
                }
            }}
        )
        print doc['_id']
