# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
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
        d['sample_number'] = row['sample_number']
        d['full_composition'] = row['full_composition']
        d['tolerance_factor'] = row['tolerance_factor']
        d['solid_solution'] = row['type of solid solution']
        d['reduced_phase'] = RecursiveDict()
        d['reduced_phase']['composition'] = row['composition reduced phase']
        d['reduced_phase']['closest_MP'] = row['closest phase MP (reduced)'].replace('n.a.', '')
        d['oxidized_phase'] = RecursiveDict()
        #d['oxidized_phase']['composition'] = row['composition oxidized phase']
        d['oxidized_phase']['closest_MP'] = row['closest phase MP (oxidized)'].replace('n.a.', '')
        d['oxidized_phase']['crystal_structure'] = row['crystal structure (fully oxidized)']
        d['Reference'] = row['Reference']

        composition = row['composition oxidized phase']
        identifier = get_composition_from_string(composition)
        mpfile.add_hierarchical_data(
            nest_dict(d, ['data']), identifier=identifier
        )

        exp_thermo = GetExpThermo(int(row['sample_number']), plotting=False)
        delta, dh, dh_err, x, dh_fit, extrapolate, abs_delta = exp_thermo.exp_dh()
        df = Table(RecursiveDict([('δ', delta), ('ΔH', dh), ('ΔHₑᵣᵣ', dh_err)]))
        mpfile.add_data_table(identifier, df, name='ΔHₒ')
        print 'DONE'
