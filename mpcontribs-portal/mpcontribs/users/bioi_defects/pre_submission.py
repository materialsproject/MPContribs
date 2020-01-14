import os, sys
from glob import glob
from pandas import read_excel, isnull, ExcelWriter, Series, to_numeric, merge
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, nest_dict, read_csv
from mpcontribs.io.archieml.mpfile import MPFile

project = 'bioi_defects'

from pymongo import MongoClient
client = MongoClient('mongodb+srv://'+os.environ['MPCONTRIBS_MONGO_HOST'])
db = client['mpcontribs']
print(db.contributions.count_documents({'project': project}))

def run(mpfile):
    identifier = mpfile.ids[0]
    xcol, ycol = 'V [V]', 'J {}°C {} [mA/cm²]'
    full_df = None
    for fn in sorted(glob(os.path.join('Data', 'Figure 4', '*_01_DIV.txt'))):
        with open(fn, 'r') as f:
            name = os.path.splitext(os.path.basename(fn))[0]
            body = '\n'.join(['\t'.join([xcol, ycol]), f.read()])
            df = read_csv(body, sep='\t').apply(to_numeric, errors='coerce').sort_values(by=[xcol])
            if full_df is None:
                full_df = df[xcol].to_frame()

            offset = 0.
            if 'fwd_dB_p3' in name:
                offset = -6.70273000E-11
            elif 'rev_dB_p3' in name:
                offset = 4.49694000E-10
            elif 'fwd_dG_p6' in name:
                offset = -8.90037000E-11
            elif 'rev_dG_p6' in name:
                offset = 8.42196000E-10

            temp = name[4:].split('CZnO', 1)[0]
            direction = 'fwd' if 'fwd' in name else 'rev'
            col = ycol.format(temp, direction)
            full_df[col] = (df[ycol] + offset).abs() * 1000. / 0.045

    mpfile.add_data_table(identifier, full_df, 'JV|dark')

mpfile = MPFile.from_file('mpfile_init.txt')
mpfile.max_contribs = 2
run(mpfile)
print(mpfile)

filename = f'{project}.txt'
mpfile.write_file(filename=filename)
mpfile = MPFile.from_file(filename)
print(len(mpfile.ids))

mpfile.document.pop('_hdata')

for idx, (identifier, content) in enumerate(mpfile.document.items()):
    doc = {'identifier': identifier, 'project': project, 'content': {}}
    doc['content']['data'] = content.pop('data')
    doc['collaborators'] = [{'name': 'Patrick Huck', 'email': 'phuck@lbl.gov'}]
    r = db.contributions.insert_one(doc)
    cid = r.inserted_id
    print(idx, ':', cid)

    tids = []
    table_names = [k for k in content.keys() if k != 'graphs']
    for name in table_names:
        print(name)
        table = mpfile.document[identifier][name]
        table.pop('@module')
        table.pop('@class')
        table['identifier'] = identifier
        table['project'] = project
        table['name'] = name
        table['cid'] = cid
        r = db.tables.insert_one(table)
        tids.append(r.inserted_id)

    print(tids)
    query = {'identifier': identifier, 'project': project}
    r = db.contributions.update_one(query, {'$set': {'content.tables': tids}})
