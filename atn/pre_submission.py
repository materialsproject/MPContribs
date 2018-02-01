# -*- coding: utf-8 -*-
import os
from mpcontribs.users.utils import duplicate_check

#@duplicate_check
def run(mpfile, **kwargs):
    from zipfile import ZipFile
    from pandas import read_csv
    from StringIO import StringIO

    zip_path = mpfile.hdata.general['input_file']
    zip_file = ZipFile(zip_path, 'r')

    for composition in mpfile.ids:
        print composition
        filename =  mpfile.hdata[composition].get('filename')
        try:
            csv = zip_file.read(filename)
            df = read_csv(StringIO(csv))
            mpfile.add_data_table(
                composition, df[['Energy', 'XAS', 'XMCD']], name='Co' # TODO name
            )
        except KeyError:
            print 'ERROR: Did not find %s in zip file' % filename
