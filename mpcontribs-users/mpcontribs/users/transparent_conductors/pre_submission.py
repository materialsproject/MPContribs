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

def run(mpfile):

    google_sheet = 'https://docs.google.com/spreadsheets/d/1bgQAdSfyrPEDI4iljwWlkyUPt_mo84jWr4N_1DKQDUI/export?format=xlsx'
    dfs = read_excel(google_sheet, sheet_name=['n-type TCs', 'p-type TCs'], header=[0, 1, 2])

    for name, df in dfs.items():
        doping = name.split(' ')[0]
        done = False
        for row in df.to_dict(orient='records'):
            identifier = None
            data = RecursiveDict()
            for keys, value in row.items():
                key = '.'.join([
                    k.replace('TC', '').strip()
                    for k in keys if not k.startswith('Unnamed:')
                ])
                if key.endswith('MP link'):
                    continue
                if key.endswith('experimental doping type'):
                    key = key.replace('Transport', 'Dopability')
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
                    clean_key = key.replace(':', '/').replace(' = ', '=').lower()
                    data[clean_key] = val

            if done:
                break
            mpfile.add_hierarchical_data(
                {'data': {doping: unflatten(data)}},
                identifier=identifier
            )

mpfile = MPFile()
mpfile.max_contribs = 90
run(mpfile)

filename='transparent_conductors.txt'
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

