# -*- coding: utf-8 -*-
import os, json
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
#from mpcontribs.users.utils import duplicate_check

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': 'screening_inorganic_pv'}))

#@duplicate_check
def run(mpfile, **kwargs):

    indir = '/Users/patrick/Downloads/ThinFilmPV'
    summary_data = json.load(open(os.path.join(indir, 'SUMMARY.json'), 'r'))
    absorption_data = json.load(open(os.path.join(indir, 'ABSORPTION.json'), 'r'))
    dos_data = json.load(open(os.path.join(indir, 'DOS.json'), 'r'))
    config = RecursiveDict([
        ('SLME_500_nm', ['SLME|500nm', '%']),
        ('SLME_1000_nm', ['SLME|1000nm', '%']),
        ('E_g', ['ΔE.corrected', 'eV']),
        ('E_g_d', ['ΔE.direct', 'eV']),
        ('E_g_da', ['ΔE.dipole-allowed', 'eV']),
        ('m_e', ['mᵉ', 'mₑ']),
        ('m_h', ['mʰ', 'mₑ'])
    ])

    print(len(summary_data.keys()))
    for mp_id, d in summary_data.items():
        print(mp_id)
        rd = RecursiveDict()
        for k, v in config.items():
            value = clean_value(d[k], v[1], max_dgts=4)
            if not '.' in v[0]:
                rd[v[0]] = value
            else:
                keys = v[0].split('.')
                if not keys[0] in rd:
                    rd[keys[0]] = RecursiveDict({keys[1]: value})
                else:
                    rd[keys[0]][keys[1]] = value

        mpfile.add_hierarchical_data({'data': rd}, identifier=mp_id)

        query = {'identifier': mp_id, 'project': 'screening_inorganic_pv'}
        doc = query.copy()
        doc['content.data'] = mpfile.document[mp_id]['data']
        doc['collaborators'] = [{'name': 'Patrick Huck', 'email': 'phuck@lbl.gov'}]
        r = db.contributions.update_one(query, {'$set': doc}, upsert=True)
        cid = r.upserted_id

        df = DataFrame(data=absorption_data[mp_id])
        df.columns = ['hν [eV]', 'α [cm⁻¹]']
        mpfile.add_data_table(mp_id, df, 'absorption')
        table = mpfile.document[mp_id]['absorption']
        table.pop('@module')
        table.pop('@class')
        table['identifier'] = mp_id
        table['project'] = 'screening_inorganic_pv'
        table['name'] = 'absorption'
        table['cid'] = cid
        r = db.tables.insert_one(table)
        tids = [r.inserted_id]

        df = DataFrame(data=dos_data[mp_id])
        df.columns = ['E [eV]', 'DOS [eV⁻¹]']
        mpfile.add_data_table(mp_id, df, 'dos')
        table = mpfile.document[mp_id]['dos']
        table.pop('@module')
        table.pop('@class')
        table['identifier'] = mp_id
        table['project'] = 'screening_inorganic_pv'
        table['name'] = 'dos'
        table['cid'] = cid
        r = db.tables.insert_one(table)
        tids.append(r.inserted_id)

        r = db.contributions.update_one(query, {'$set': {'content.tables': tids}})

from mpcontribs.io.archieml.mpfile import MPFile
mpfile = MPFile()
mpfile.max_contribs = 790
run(mpfile)
#print(mpfile)
