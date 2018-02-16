# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from glob import glob
import pandas as pd
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, read_csv, nest_dict
from mpcontribs.io.core.components import Table
from mpcontribs.users.utils import duplicate_check

def get_table(results, letter):
    y = 'Δ{}'.format(letter)
    df = Table(RecursiveDict([
        ('δ', results[0]), (y, results[1]), (y+'ₑᵣᵣ', results[2])
    ]))
    x0, x1 = map(float, df['δ'].iloc[[0,-1]])
    pad = 0.1 * (x1 - x0)
    mask = (results[3] > x0 - pad) & (results[3] < x1 + pad)
    x, fit = results[3][mask], results[4][mask]
    df.set_index('δ', inplace=True)
    df2 = pd.DataFrame(RecursiveDict([
        ('δ', x), (y+' Fit', fit)
    ]))
    df2.set_index('δ', inplace=True)
    cols = ['δ', y, y+'ₑᵣᵣ', y+' Fit']
    return pd.concat([df, df2]).sort_index().reset_index().rename(
        columns={'index': 'δ'}).fillna('')[cols]

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
        enthalpy = exp_thermo.exp_dh()
        table = get_table(enthalpy, 'H')
        mpfile.add_data_table(identifier, table, name='enthalpy')

        print 'add ΔS ...'
        entropy = exp_thermo.exp_ds()
        table = get_table(entropy, 'S')
        mpfile.add_data_table(identifier, table, name='entropy')

        print 'add raw data ...'
        tga_results = os.path.join(os.path.dirname(__file__), 'solar_perovskite', 'tga_results')
        for path in glob(os.path.join(tga_results, 'ExpDat_JV_P_{}_*.csv'.format(sample_number))):
            print path.split('_{}_'.format(sample_number))[-1].split('.')[0], '...'
            body = open(path, 'r').read()
            cols = ['Time [min]', 'Temperature [C]', 'dm [%]', 'pO2']
            table = read_csv(body, lineterminator=os.linesep, usecols=cols, skiprows=5)
            table = table[cols].iloc[::100, :]
            mpfile.add_data_table(identifier, table, name='raw')

        print 'DONE'
