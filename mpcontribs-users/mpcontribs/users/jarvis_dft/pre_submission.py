# -*- coding: utf-8 -*-
import os, tarfile, json, urllib, gzip, sys
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from monty.json import MontyDecoder
#from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.utils import clean_value, get_composition_from_string

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': 'jarvis_dft'}))

#@duplicate_check
def run(mpfile, **kwargs):
    from pymatgen import Structure

    reference_project = None
    input_data, input_keys, extra = RecursiveDict(), RecursiveDict(), RecursiveDict()
    #input_urls = mpfile.document['_hdata'].pop('input_urls')
    input_urls = {
        'NUS': {
            "file": "http://www.2dmatpedia.org/static/db.json.gz",
            "detail": "http://www.2dmatpedia.org/2dmaterials/doc/{}"
        },
        'JARVIS': {
            "file": "https://www.ctcms.nist.gov/~knc6/jdft_{}.json.tgz",
            "detail": "https://www.ctcms.nist.gov/~knc6/jsmol/{}.html"
        }
    }

    for project in input_urls:
        input_url = input_urls[project]['file']
        if '{}' in input_url:
            input_url = input_url.format('2d') # TODO 3d for Jarvis

        #dbfile = os.path.join(os.environ['HOME'], 'work', input_url.rsplit('/')[-1])
        dbfile = input_url.rsplit('/')[-1]
        if not os.path.exists(dbfile):
            print('downloading', dbfile, '...')
            urllib.request.urlretrieve(input_url, dbfile)

        ext = os.path.splitext(dbfile)[1]
        is_nus = bool(ext == '.gz')
        id_key = 'source_id' if is_nus else 'mpid'
        if not is_nus:
            with tarfile.open(dbfile, "r:gz") as tar:
                member = tar.getmembers()[0]
                raw_data = json.load(tar.extractfile(member), cls=MontyDecoder)
        else:
            reference_project = project
            raw_data = []
            with gzip.open(dbfile, 'rb') as f:
                for line in f:
                    raw_data.append(json.loads(line, cls=MontyDecoder))
        input_data[project] = RecursiveDict((d[id_key], d) for d in raw_data)

        input_keys[project] = [
            'material_id', 'exfoliation_energy_per_atom', 'structure'
        ] if is_nus else ['jid', 'exfoliation_en', 'final_str']
        extra[project] = [
            ('fin_en', ('E', 'meV/atom')),
            ('op_gap', ('ΔE|optB88vdW', 'meV/atom')),
            ('mbj_gap', ('ΔE|mbj', 'meV/atom')),
            #('kv', ('Kᵥ', 'GPa')),
            #('gv', ('Gᵥ', 'GPa'))
        ] if not is_nus else []

        print(len(input_data[project]), 'materials loaded for', project)

    projects = input_data.keys()
    identifiers = []
    for d in input_data.values():
        identifiers += list(d.keys())

    for identifier in set(identifiers):
        print(identifier)
        data, structures = RecursiveDict(), RecursiveDict()

        for project in projects:
            if project not in data:
                data[project] = RecursiveDict()
            if identifier in input_data[project]:
                d = input_data[project][identifier]
                structures[project] = d[input_keys[project][-1]]
                if data.get('formula') is None:
                    data['formula'] = get_composition_from_string(
                        structures[project].composition.reduced_formula
                    )
                data[project]['id'] = input_urls[project]['detail'].format(d[input_keys[project][0]])
                if input_keys[project][1] in d:
                    Ex = d[input_keys[project][1]]
                    if project == reference_project:
                        Ex *= 1000.
                    data[project]['Eₓ'] = clean_value(Ex, 'eV')
                for k, (sym, unit) in extra[project]:
                    if d[k] != 'na':
                        data[project][sym] = clean_value(d[k], unit)

        mpfile.add_hierarchical_data(nest_dict(data, ['data']), identifier=identifier)
        #r = db.contributions.update_one(
        #    {'identifier': identifier, 'project': 'jarvis_dft'},
        #    {'$set': {'content.data': mpfile.document[identifier]['data']}},
        #    upsert=True
        #)
        #print(r.matched_count, r.modified_count, r.upserted_id)

        doc = db.contributions.find_one(
            {'identifier': identifier, 'project': 'jarvis_dft'},
            {'_id': 1, 'content.structures': 1}
        )
        if 'structures' in doc['content']:
            print('structures already added for', identifier)
            continue
        print(doc['_id'])

        inserted_ids = []
        for project, structure in structures.items():
            try:
                mpfile.add_structure(structure, name=project, identifier=identifier)
                sdct = mpfile.document[identifier]['structures'][project]
                sdct.pop('@module')
                sdct.pop('@class')
                if sdct['charge'] is None:
                    sdct.pop('charge')
                sdct['identifier'] = identifier
                sdct['project'] = 'jarvis_dft'
                sdct['name'] = project
                sdct['cid'] = doc['_id']
                r = db.structures.insert_one(sdct)
                inserted_ids.append(r.inserted_id)
            except Exception as ex:
                print(str(ex))

        print(inserted_ids)
        r = db.contributions.update_one(
            {'_id': doc['_id']},
            {'$set': {'content.structures': inserted_ids}}
        )
        print(r.matched_count, r.modified_count)

from mpcontribs.io.archieml.mpfile import MPFile
mpfile = MPFile()
mpfile.max_contribs = 3200
run(mpfile)
