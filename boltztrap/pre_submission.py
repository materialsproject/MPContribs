# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, gzip, json
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict, clean_value
from mpcontribs.users.boltztrap.rest.rester import BoltztrapRester
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.components import Table

try:
    from os import scandir # python3
except ImportError:
    from scandir import scandir

@duplicate_check
def run(mpfile, **kwargs):

    # extract data from json files
    keys = ['pretty_formula', 'volume']
    input_dir = mpfile.hdata.general['input_dir']
    for idx, obj in enumerate(scandir(input_dir)):
        mpid = obj.name.split('.', 1)[0].rsplit('_', 1)[1]
        print(mpid)
        input_file = gzip.open(obj.path, 'rb')
        try:
            data = json.loads(input_file.read())

            # filter out metals
            if 'GGA' not in data['gap'] or data['gap']['GGA'] < 0.1:
                print('GGA gap < 0.1 -> skip')
                continue

            # add hierarchical data (nested key-values)
            hdata = RecursiveDict()

            cond_eff_mass = 'mₑᶜᵒⁿᵈ'
            hdata[cond_eff_mass] = RecursiveDict()
            names = ['e₁', 'e₂', 'e₃', '<m>']
            if 'GGA' not in data:
                print('no GGA key for', mpid)
                continue
            for dt, d in data['GGA']['cond_eff_mass'].items():
                eff_mass = d['300']['1e+18']
                eff_mass.append(np.mean(eff_mass))
                hdata[cond_eff_mass][dt] = RecursiveDict(
                    (names[idx], clean_value(x, 'mₑ'))
                    for idx, x in enumerate(eff_mass)
                )

            seebeck_fix_dop_temp = "Seebeck"
            hdata[seebeck_fix_dop_temp] = RecursiveDict()
            cols = ['e₁', 'e₂', 'e₃', 'temperature', 'doping']
            for doping_type in ['p', 'n']:
                sbk = map(float, data['GGA']['seebeck_doping'][doping_type]['300']['1e+18']['eigs'])
                vals = [clean_value(s, 'μV/K') for s in sbk] + ['300 K', '10¹⁸ cm⁻³']
                hdata[seebeck_fix_dop_temp][doping_type] = RecursiveDict(
                        (k, v) for k, v in zip(cols, vals))

            mpfile_data = nest_dict(hdata, ['data'])

            # build data and max values for seebeck, conductivity and kappa
            # max/min values computed using numpy. It may be better to code it in pure python.
            hdata = RecursiveDict((k, data[k]) for k in keys)
            hdata['volume'] = clean_value(hdata['volume'], 'Å³')
            cols = ['value', 'temperature', 'doping']
            tables = RecursiveDict()
            props = RecursiveDict()
            props['seebeck_doping'] = ['S', 'μV/K']
            props['cond_doping'] = ['σ', '(Ωms)⁻¹']
            props['kappa_doping'] = ['κₑ', 'W/(mKs)']

            for prop_name, (lbl, unit) in props.iteritems():
                # TODO install Symbola font if you see squares here (https://fonts2u.com/symbola.font)
                # and select it as standard font in your browser (leave other fonts as is, esp. fixed width)
                tables[lbl] = RecursiveDict()
                hlbl = lbl+'₋' if len(lbl) > 1 else lbl
                hlbl += 'ₑₓₜᵣ'
                hdata[hlbl] = RecursiveDict()

                for doping_type in ['p', 'n']:
                    prop = data['GGA'][prop_name][doping_type]
                    prop_averages, dopings, columns = [], None, ['T [K]']
                    temps = sorted(map(int, prop.keys()))
                    for temp in temps:
                        row = [temp]
                        if dopings is None:
                            dopings = sorted(map(float, prop[str(temp)].keys()))
                        for doping in dopings:
                            doping_str = '%.0e' % doping
                            if len(columns) <= len(dopings):
                                columns.append('{} cm⁻³ [{}]'.format(doping_str, unit))
                            eigs = prop[str(temp)][doping_str]['eigs']
                            row.append(np.mean(eigs))
                        prop_averages.append((temp, row))

                    tables[lbl][doping_type] = Table.from_items(
                        prop_averages, orient='index', columns=columns
                    )

                    arr_prop_avg = np.array([item[1] for item in prop_averages])[:,1:]
                    max_v = np.max(arr_prop_avg)
                    if prop_name[0] == 's' and doping_type == 'n':
                        max_v = np.min(arr_prop_avg)
                    if prop_name[0] == 'k':
                        max_v = np.min(arr_prop_avg)
                    arg_max = np.argwhere(arr_prop_avg==max_v)[0]

                    vals = [
                        clean_value(max_v, unit),
                        clean_value(temps[arg_max[0]], 'K'),
                        clean_value(dopings[arg_max[1]], 'cm⁻³')
                    ]
                    hdata[hlbl][doping_type] = RecursiveDict(
                        (k, v) for k, v in zip(cols, vals)
                    )

            mpfile_data.rec_update(nest_dict(hdata, ['extra_data']))
            mpfile.add_hierarchical_data(mpfile_data, identifier=data['mp_id'])
            for lbl, dct in tables.iteritems():
                for doping_type, table in dct.iteritems():
                    mpfile.add_data_table(
                        data['mp_id'], table, name='{}({})'.format(lbl, doping_type)
                    )

        finally:
            input_file.close()
