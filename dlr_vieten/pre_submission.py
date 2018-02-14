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
    input_file = os.path.join(
        os.path.dirname(__file__), mpfile.hdata.general['input_file']
    )
    table = read_csv(open(input_file, 'r').read())
    dct = super(Table, table).to_dict(orient='records', into=RecursiveDict)
    for row in dct:
        composition = row['full_composition'].replace('Ox', '')
        identifier = get_composition_from_string(composition)
        mpfile.add_hierarchical_data(
            nest_dict(row, ['data']), identifier=identifier
        )
