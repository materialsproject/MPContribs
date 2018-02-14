# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from zipfile import ZipFile
from StringIO import StringIO
from scipy import where
from decimal import Decimal
from scipy.interpolate import interp1d, interp2d
from pandas import to_numeric
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.utils import read_csv, clean_value
from mpcontribs.io.core.components import Table
from mpcontribs.io.core.utils import nest_dict, get_composition_from_string

def get_concentration_functions(composition_table_dict):

    meta = composition_table_dict['meta']
    composition_table = Table.from_dict(composition_table_dict['data'])
    elements = [col for col in composition_table.columns if col not in meta]
    x = composition_table["X"].values
    y = composition_table["Y"].values
    cats = composition_table["X"].unique()
    concentration, conc, d, y_c, functions = {}, {}, {}, {}, RecursiveDict()

    for el in elements:
        concentration[el] = to_numeric(composition_table[el].values)/100.
        conc[el], d[el], y_c[el] = {}, {}, {}

        if meta['X'] == 'category':
            for i in cats:
                k = '{:06.2f}'.format(float(i))
                y_c[el][k] = to_numeric(y[where(x==i)])
                conc[el][k] = to_numeric(concentration[el][where(x==i)])
                d[el][k] = interp1d(y_c[el][k], conc[el][k])

            functions[el] = lambda a, b, el=el: d[el][a](b)

        else:
            functions[el] = interp2d(float(x), float(y), concentration[el])

    return functions

@duplicate_check
def run(mpfile, **kwargs):

    input_file = mpfile.document['_hdata'].pop('input_file')
    zip_path = os.path.join(os.environ['HOME'], 'work', input_file)
    if not os.path.exists(zip_path):
        return 'Please upload', zip_path
    zip_file = ZipFile(zip_path, 'r')

    composition_table_dict = mpfile.document['_hdata']['composition_table']
    conc_funcs = get_concentration_functions(composition_table_dict)

    for info in zip_file.infolist():
        print info.filename
        d = RecursiveDict()

        # positions.x/y from filename, <scan-id>_<meas-element>_<X>_<Y>.csv
        element, x, y = os.path.splitext(info.filename)[0].rsplit('_', 4)
        d['position'] = RecursiveDict(
            (k, clean_value(v, 'mm'))
            for k, v in zip(['x', 'y'], [x, y])
        )

        # composition
        d['composition'] = RecursiveDict(
            (el, clean_value(f(x, y), convert_to_percent=True))
            for el, f in conc_funcs.items()
        )

        # identifier
        identifier = get_composition_from_string(''.join([
            '{}{}'.format(el, int(round(Decimal(comp.split()[0]))))
            for el, comp in d['composition'].items()
        ]))

        # load csv file
        try:
            csv = zip_file.read(info.filename)
        except KeyError:
            print 'ERROR: Did not find %s in zip file' % info.filename

        # read csv to pandas DataFrame and add to MPFile
        df = read_csv(csv)
        df = df[['Energy', 'XAS', 'XMCD']]

        # min and max
        d.rec_update(RecursiveDict(
            (y, RecursiveDict([
                ('min', df[y].min()), ('max', df[y].max())
            ])) for y in ['XAS', 'XMCD']
        ))

        # add data to MPFile
        mpfile.add_hierarchical_data(nest_dict(d, ['data']), identifier=identifier)
        mpfile.add_data_table(identifier, df, name=element)
