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

        #d['oxidized_phase']['closest_MP'] = row['closest phase MP (oxidized)'].replace('n.a.', '')
        # finish calculations for mp-id; fake until then ;)
        composition = row['composition oxidized phase']
        identifier = get_composition_from_string(composition) # TODO oxidized phase mp-id
        print identifier

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

        mpfile.add_hierarchical_data(
            nest_dict(d, ['data']), identifier=identifier
        )

        print 'add ΔH ...'
        sample_number = int(row['sample_number'])
        exp_thermo = GetExpThermo(sample_number, plotting=False)
        delta, dh, dh_err, x, dh_fit, extrapolate, abs_delta = exp_thermo.exp_dh()
        df = Table(RecursiveDict([('δ', delta), ('ΔH', dh), ('ΔHₑᵣᵣ', dh_err)]))
        mpfile.add_data_table(identifier, df, name='ΔHₒ')

        print 'add ΔS ...'
        delta, ds, ds_err, x, ds_fit, extrapolate, abs_delta = exp_thermo.exp_ds()
        df = Table(RecursiveDict([('δ', delta), ('ΔS', ds), ('ΔSₑᵣᵣ', ds_err)]))
        mpfile.add_data_table(identifier, df, name='ΔSₒ')

        print 'add raw data ...'
        tga_results = os.path.join(os.path.dirname(__file__), 'solar_perovskite', 'tga_results')
        for path in glob(os.path.join(tga_results, 'ExpDat_JV_P_{}_*.csv'.format(sample_number))):
            print path.split('_{}_'.format(sample_number))[-1].split('.')[0], '...'
            body = open(path, 'r').read()
            cols = ['Time [min]', 'Temperature [C]', 'dm [%]', 'pO2']
            table = read_csv(body, lineterminator=os.linesep, usecols=cols, skiprows=5)
            table = table[cols].iloc[::100, :]
            mpfile.add_data_table(identifier, table, name='raw_data')

        print 'DONE'
