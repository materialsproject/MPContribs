# -*- coding: utf-8 -*-
import os
#from mpcontribs.users.utils import duplicate_check

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': 'esters'}))

#@duplicate_check
def run(mpfile, **kwargs):
    identifier = 'mp-27902' #mpfile.ids[0]
    doc = db.contributions.find_one(
        {'identifier': identifier, 'project': 'esters'},
        {'_id': 1, 'content.structures': 1}
    )
    if 'structures' in doc['content']:
        print('structures already added for', identifier)
        return

    print(doc['_id'])
    contcar = os.path.join(os.path.dirname(__file__), 'CONTCAR')
    input_string = open(contcar, 'r').read()
    name = 'BiSe'
    mpfile.add_structure(input_string, name=name, identifier=identifier, fmt='poscar')
    sdct = mpfile.document[identifier]['structures'][name]
    sdct.pop('@module')
    sdct.pop('@class')
    if sdct['charge'] is None:
        sdct.pop('charge')
    sdct['identifier'] = identifier
    sdct['project'] = 'esters'
    sdct['name'] = name
    sdct['cid'] = doc['_id']
    r = db.structures.insert_one(sdct)
    print(r.inserted_id)

    r = db.contributions.update_one(
        {'_id': doc['_id']},
        {'$set': {'content.structures': [r.inserted_id]}}
    )
    print(r.matched_count, r.modified_count)

from mpcontribs.io.archieml.mpfile import MPFile
mpfile = MPFile()
mpfile.max_contribs = 1
run(mpfile)
print(mpfile)
