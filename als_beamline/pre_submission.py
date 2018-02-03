# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from decimal import Decimal
from zipfile import ZipFile
from StringIO import StringIO
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.utils import read_csv, clean_value
from mpcontribs.io.core.components import Table

@duplicate_check
def run(mpfile, **kwargs):

    input_file = mpfile.document['_hdata'].pop('input_file')
    zip_path = os.path.join(os.environ['HOME'], 'work', input_file)
    if not os.path.exists(zip_path):
        return 'Please upload', zip_path
    zip_file = ZipFile(zip_path, 'r')

    # pop all compositions to only submit processed contributions
    # TODO: this could be skipped if positions in filename were automatically
    #       converted to compositions
    config = RecursiveDict(
        (composition, mpfile.document.pop(composition))
        for composition in mpfile.ids
    )

    for composition, data in config.items():
        print composition
        d = RecursiveDict()

        # reset compositions to use % and clean_value
        d['composition'] = RecursiveDict(
            (k, clean_value(v, convert_to_percent=True))
            for k, v in data['composition'].items()
        )

        # get positions.x/y from filename, e.g. Co_(-08.50,082.60).csv
        name, xy = os.path.splitext(data['filename'])[0].split('_')
        d['position'] = RecursiveDict(
            (k, clean_value(v, 'mm'))
            for k, v in zip(['x', 'y'], xy[1:-1].split(','))
        )

        # add hierarchical data to MPFile
        mpfile.add_hierarchical_data(d, identifier=composition)

        # load csv file
        try:
            csv = zip_file.read(data['filename'])
        except KeyError:
            print 'ERROR: Did not find %s in zip file' % data['filename']

        # read csv to pandas DataFrame and add to MPFile
        df = read_csv(csv)
        df = df[['Energy', 'XAS', 'XMCD']]
        #print df.from_dict(df.to_dict())
        mpfile.add_data_table(composition, df, name=name)
