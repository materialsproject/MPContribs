import zipfile, os
from pandas import read_csv
from StringIO import StringIO
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles

def run(mpfile, nmax=None):
    meta_data = mpfile.hdata[mp_level01_titles[0]]
    zipfile_path = meta_data['zipfile_path']
    table_columns = meta_data['table_columns'].split(' -- ')
    zf = zipfile.ZipFile(zipfile_path, 'r')

    for idx, file_path in enumerate(zf.namelist()):
        file_name, file_extension = os.path.splitext(file_path)
        if file_name == 'readme' or '800nm' in file_name or 'ML' in file_name:
            continue
        df = read_csv(StringIO(zf.read(file_path)), sep='\t', header=None, names=table_columns)
        mpfile.add_data_table(mpfile.ids[0], df, file_name)
        print 'added data from', file_name
        if nmax and idx >= nmax-1:
            break
