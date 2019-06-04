import tarfile, os
from pandas import read_excel
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict

project = 'perovskites_diffusion'

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': project}))

def run(mpfile):

    google_sheet = 'https://docs.google.com/spreadsheets/d/1Wep4LZjehrxu3Cl5KJFvAAhKhP92o4K5aC-kZYjGz2o/export?format=xlsx'
    contcars_filepath = 'bulk_CONTCARs.tar.gz'
    contcars = tarfile.open(contcars_filepath)

    df = read_excel(google_sheet)
    keys = df.iloc[[0]].to_dict(orient='records')[0]
    abbreviations = RecursiveDict()

    count, skipped, update = 0, 0, 0
    for index, row in df[1:].iterrows():
        mpid = None
        data = RecursiveDict()
        mpfile_single = MPFile()

        for col, value in row.iteritems():
            if col == 'level_0' or col == 'index':
                continue
            key = keys[col]
            if isinstance(key, str):
                key = key.strip()
                if not key in abbreviations:
                    abbreviations[key] = col
            else:
                key = col.strip().lower()

            if key == 'pmgmatchid':
                mpid = value.strip()
                if mpid == 'None':
                    mpid = None
                name = '_'.join(data['directory'].split('/')[1:])
                contcar_path = 'bulk_CONTCARs/{}_CONTCAR'.format(
                    data['directory'].replace('/', '_')
                )
                contcar = contcars.extractfile(contcar_path)
                mpid_match = mpfile_single.add_structure(
                    contcar.read(), fmt='poscar',
                    name=name, identifier=mpid
                )
                #if not mp_id_pattern.match(mpid_match):
                #    print('skipping', name)
                #    continue
                mpid = mpid_match
            else:
                data[key] = value

        if mpid is None:
            continue

        mpfile_single.add_hierarchical_data({'data': data}, identifier=mpid)

        mpfile.concat(mpfile_single)

    mpfile.add_hierarchical_data({'abbreviations': abbreviations})

mpfile = MPFile()
mpfile.max_contribs = 1
run(mpfile)
print(mpfile)
