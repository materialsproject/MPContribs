import zipfile, os
from pandas import read_csv
from StringIO import StringIO
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):
    meta_data = mpfile.document['_hdata'].pop('input')
    csv_path = os.path.join(os.environ['HOME'], 'work', meta_data['csv_path'])
    if not os.path.exists(csv_path):
        return 'Please upload', csv_path
    table_columns = meta_data['table_columns'].split(' -- ')
    df = read_csv(csv_path, names=table_columns)
    mpfile.add_data_table(mpfile.ids[0], df, 'main_table')
    print('Added data from {}'.format(csv_path))
