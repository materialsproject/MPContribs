from pymongo import MongoClient
host, port, db_name = 'localhost', 27017, 'user_contributions'
username, password = 'test', 'test'
client = MongoClient(host, port, j=False)
client[db_name].authenticate(username, password)
db = client[db_name].contributions
# NOTE: distinguish mp cat's by format of mp_cat_id
pipeline = [
    { '$group': {
        '_id': '$mp_cat_id',
        'num_contribs': { '$sum': 1 },
        'contrib_ids': { '$addToSet': '$contribution_id' }
    }}
]
for doc in db.aggregate(pipeline, cursor={}):
    print doc
