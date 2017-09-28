import os, gzip, json
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.users.boltztrap.rest.rester import BoltztrapRester

def run(mpfile, nmax=5, dup_check_test_site=True):

    # book-keeping
    existing_mpids = {}
    for b in [False, True]:
        with BoltztrapRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.query):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    # extract data from json files
    keys = ['pretty_formula', 'volume']
    input_dir = mpfile.hdata.general['input_dir']
    for idx, fn in enumerate(os.listdir(input_dir)):
        print(fn)
        input_file = gzip.open(os.path.join(input_dir, fn), 'rb')
        try:
            data = json.loads(input_file.read())

            # add hierarchical data (nested key-values)
            # TODO: extreme values for Seebeck, conductivity, power factor, zT, effective mass
            mpfile.add_hierarchical_data(
                RecursiveDict((k, data[k]) for k in keys),
                identifier=data['mp_id']
            )

            # add structure; TODO necessary only if not canonical from MP
            #name = get_composition_from_string(data['pretty_formula'])
            #mpfile.add_structure(
            #    data['cif_structure'], name=name,
            #    identifier=data['mp_id'], fmt='cif'
            #)

            # add data table
            for doping_type in ['n', 'p']:
                seebeck = data['GGA']['seebeck_doping'][doping_type]
                seebeck_averages, dopings, columns = [], None, ['T']
                temps = sorted(map(int, seebeck.keys()))
                for temp in temps:
                    row = ['{} K'.format(temp)]
                    if dopings is None:
                        dopings = sorted(map(float, seebeck[str(temp)].keys()))
                    for doping in dopings:
                        doping_str = '%.0e' % doping
                        if len(columns) <= len(dopings):
                            columns.append(doping_str + ' cm-3')
                        eigs = seebeck[str(temp)][doping_str]['eigs']
                        row.append(np.mean(eigs))
                    seebeck_averages.append(row)
                df = DataFrame.from_records(seebeck_averages, columns=columns)
                table_name = doping_type + '-type average seeback'
                mpfile.add_data_table(data['mp_id'], df, table_name)

        finally:
            input_file.close()
        if idx >= nmax+1:
            break
