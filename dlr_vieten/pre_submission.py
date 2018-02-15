# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from glob import glob
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, read_csv, nest_dict
from mpcontribs.io.core.components import Table
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):
    # TODO clone solar_perovskite if needed, abort if insufficient permissions
    from .solar_perovskite.core import GetExpThermo

    input_file = mpfile.hdata.general['input_file']
    input_file = os.path.join(os.path.dirname(__file__), input_file)
    table = read_csv(open(input_file, 'r').read().replace(';', ','))
    dct = super(Table, table).to_dict(orient='records', into=RecursiveDict)

    for row in dct:

        d = RecursiveDict()
        #d['full_composition'] = row['full_composition']
        d['tolerance_factor'] = row['tolerance_factor']
        d['solid_solution'] = row['type of solid solution']
        d['oxidized_phase'] = RecursiveDict()
        d['oxidized_phase']['composition'] = row['composition oxidized phase']
        d['oxidized_phase']['crystal_structure'] = row['crystal structure (fully oxidized)']
        d['reduced_phase'] = RecursiveDict()
        d['reduced_phase']['composition'] = row['composition reduced phase']
        d['reduced_phase']['closest_MP'] = row['closest phase MP (reduced)'].replace('n.a.', '')
        d['Reference'] = row['Reference']
        d['sample_number'] = row['sample_number']

        #d['oxidized_phase']['closest_MP'] = row['closest phase MP (oxidized)'].replace('n.a.', '')
        # finish calculations for mp-id; fake until then ;)
        composition = d['oxidized_phase']['composition']
        identifier = get_composition_from_string(composition) # TODO oxidized phase mp-id
        mpfile.add_hierarchical_data(
            nest_dict(d, ['data']), identifier=identifier
        )

        sample_number = int(row['sample_number'])
        exp_thermo = GetExpThermo(sample_number, plotting=False)
        delta, dh, dh_err, x, dh_fit, extrapolate, abs_delta = exp_thermo.exp_dh()
        df = Table(RecursiveDict([('δ', delta), ('ΔH', dh), ('ΔHₑᵣᵣ', dh_err)]))
        mpfile.add_data_table(identifier, df, name='ΔHₒ')

        delta, ds, ds_err, x, ds_fit, extrapolate, abs_delta = exp_thermo.exp_ds()
        df = Table(RecursiveDict([('δ', delta), ('ΔS', ds), ('ΔSₑᵣᵣ', ds_err)]))
        mpfile.add_data_table(identifier, df, name='ΔSₒ')

        #for path in glob('solar_perovskite/tga_results/ExpDat_JV_P_{}_*.csv'.format(sample_number)):
        #    print path
        #    body = open(path).read()
        #    cols = ['Time [min]', 'Temperature [C]']#, 'dm [%]']#, 'pO2']
        #    # TODO show secondary y-axes in graph if column values differ by more than an order of magnitude
        #    table = read_csv(body, usecols=cols)#, skiprows=5)
        #    table = Table(table[cols].iloc[::200, :])
        #    print table.head()
        #    mpfile.add_data_table(identifier, table, name='raw_data')
        #    print mpfile.tdata[identifier]['raw_data']
        #    break



        print 'DONE'
