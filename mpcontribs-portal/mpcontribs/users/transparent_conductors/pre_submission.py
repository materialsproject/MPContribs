import tarfile, os
from pandas import read_excel
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
from mpcontribs.users.utils import unflatten
import numpy as np

project = 'transparent_conductors'

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': project}))

def run(mpfile, sheet_name):

    google_sheet = 'https://docs.google.com/spreadsheets/d/1bgQAdSfyrPEDI4iljwWlkyUPt_mo84jWr4N_1DKQDUI/export?format=xlsx'
    df = read_excel(google_sheet, sheet_name=sheet_name, header=[0, 1, 2])

    doping = sheet_name.split(' ')[0]
    done = False
    for row in df.to_dict(orient='records'):
        identifier = None
        data = RecursiveDict({'doping': doping})
        for keys, value in row.items():
            key = '.'.join([
                k.replace('TC', '').strip()
                for k in keys if not k.startswith('Unnamed:')
            ])
            if key.endswith('experimental doping type'):
                key = key.replace('Transport.', '')
            key_split = key.split('.')
            if len(key_split) > 2:
                key = '.'.join(key_split[1:])
            if key.endswith('MP link') or key.endswith('range'):
                continue
            if key.endswith('google scholar'):
                key = key.replace('.google scholar', '')
            if key == 'Material.mpid':
                if identifier is None:
                    if not isinstance(value, str) and np.isnan(value):
                        done = True
                        break
                    identifier = value.strip()
                    print(identifier)
            else:
                if key == 'Material.p pretty formula':
                    key = 'formula'
                if isinstance(value, str):
                    val = value.strip()
                else:
                    if isinstance(value, float) and np.isnan(value):
                        continue
                    if key.endswith(')'):
                        key, unit = key.rsplit(' (', 1)
                        unit = unit[:-1].replace('^-3', '⁻³').replace('^20', '²⁰')
                        if ',' in unit:
                            extra_key = key.rsplit('.', 1)[0].lower() + '.conditions'
                            data[extra_key] = unit
                            unit = ''
                        val = clean_value(value, unit=unit)
                    else:
                        val = clean_value(value)
                if not val:
                    continue
                clean_key = key.replace(' for VB:CB = 4:2', '').replace('?', '').lower()
                data[clean_key] = val

        if done:
            break
        mpfile.add_hierarchical_data(
            {'data': unflatten(data)},
            identifier=identifier
        )


for sheet_name in ['n-type TCs', 'p-type TCs']:
    doping = sheet_name.split(' ')[0]
    mpfile = MPFile()
    mpfile.max_contribs = 50
    run(mpfile, sheet_name)
    filename = f'transparent_conductors_{doping}.txt'
    mpfile.write_file(filename=filename)
    mpfile = MPFile.from_file(filename)
    print(len(mpfile.ids))

    for idx, (identifier, content) in enumerate(mpfile.document.items()):
        doc = {'identifier': identifier, 'project': project, 'content': {}}
        doc['content']['data'] = content['data']
        doc['collaborators'] = [{'name': 'Patrick Huck', 'email': 'phuck@lbl.gov'}]
        r = db.contributions.insert_one(doc)
        cid = r.inserted_id
        print(idx, ':', cid)

