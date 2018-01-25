# -*- coding: utf-8 -*-
import os, gzip, json
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from mpcontribs.users.boltztrap.rest.rester import BoltztrapRester
from mpcontribs.users.utils import clean_value, duplicate_check

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
            
            #filter out metals
            if data['gap']['GGA'] < 0.1:
                return
            
            # add hierarchical data (nested key-values)
            # TODO: extreme values for power factor, zT, effective mass
            # TODO: add a text for the description of each table
            hdata = RecursiveDict((k, data[k]) for k in keys)
            cond_eff_mass = u'mₑᶜᵒⁿᵈ'
            hdata[cond_eff_mass] = RecursiveDict()
            names = [u'e₁', u'e₂', u'e₃', u'<m>']
            for dt, d in data['GGA']['cond_eff_mass'].items():
                eff_mass = d['300']['1e+18']
                eff_mass.append(np.mean(eff_mass))
                hdata[cond_eff_mass][dt] = RecursiveDict(
                    (names[idx], u'{:.2f} mₑ'.format(x))
                    for idx, x in enumerate(eff_mass)
                )
            seebeck_fix_dop_temp = "Seebeck"
            hdata[seebeck_fix_dop_temp] = RecursiveDict()
            cols = ['e₁','e₂','e₃', 'temperature', 'doping']
            for doping_type in ['p', 'n']:
                sbk=[float(i) for i in data['GGA']['seebeck_doping'][doping_type]['300']['1e+18']['eigs']]
                vals = [u'{:.2e} μV/K'.format(s) for s in sbk] + [u'{} K'.format('300'), u'{} cm⁻³'.format('1e+18')]
                hdata[seebeck_fix_dop_temp][doping_type] = RecursiveDict(
                            (k, v) for k, v in zip(cols, vals))


            # build data and max values for seebeck, conductivity and kappa
            # max/min values computed using numpy. It may be better to code it in pure python.
            cols = ['value', 'temperature', 'doping']
            for prop_name in ['seebeck_doping', 'cond_doping', 'kappa_doping']:
                # TODO install Symbola font if you see squares here (https://fonts2u.com/symbola.font)
                # and select it as standard font in your browser (leave other fonts as is, esp. fixed width)
                if prop_name[0] == 's':
                    lbl, unit = u"Sₘₐₓ", u"μV/K"
                elif prop_name[0] == 'c':
                    lbl, unit = u"σₘₐₓ", u"(Ωms)⁻¹"
                elif prop_name[0] == 'k':
                    lbl, unit = u"κₑ₋ₘᵢₙ", u"W/(mKs)"
                hdata[lbl] = RecursiveDict()

                for doping_type in ['p', 'n']:
                    prop = data['GGA'][prop_name][doping_type]
                    prop_averages, dopings, columns = [], None, ['T (K)']
                    temps = sorted(map(int, prop.keys()))
                    for temp in temps:
                        row = [temp]
                        if dopings is None:
                            dopings = sorted(map(float, prop[str(temp)].keys()))
                        for doping in dopings:
                            doping_str = '%.0e' % doping
                            if len(columns) <= len(dopings):
                                columns.append(doping_str + u' cm⁻³')
                            eigs = prop[str(temp)][doping_str]['eigs']
                            row.append(np.mean(eigs))
                        prop_averages.append(row)

                    arr_prop_avg = np.array(prop_averages)[:,1:]
                    max_v = np.max(arr_prop_avg)
                    if prop_name[0] == 's' and doping_type == 'n':
                        max_v = np.min(arr_prop_avg)
                    if prop_name[0] == 'k':
                        max_v = np.min(arr_prop_avg)
                    arg_max = np.argwhere(arr_prop_avg==max_v)[0]

                    vals = [
                        u'{:.2e} {}'.format(max_v, unit),
                        u'{:.2e} K'.format(temps[arg_max[0]]),
                        u'{:.2e} cm⁻³'.format(dopings[arg_max[1]])
                    ]
                    hdata[lbl][doping_type] = RecursiveDict(
                        (k, v) for k, v in zip(cols, vals)
                    )

            mpfile.add_hierarchical_data(
                nest_dict(hdata, ['data']), identifier=data['mp_id']
            )

        finally:
            input_file.close()
