# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, nest_dict
from mpcontribs.io.core.utils import get_composition_from_string

@duplicate_check
def run(mpfile, **kwargs):
    from pymatgen import MPRester, Composition
    import pandas as pd

    input_file = mpfile.document['_hdata'].pop('input_file')
    file_path = os.path.join(os.environ['HOME'], 'work', input_file)
    if not os.path.exists(file_path):
        return 'Please upload', file_path
    df_dct = pd.read_excel(file_path)
    columns_units = [
        ('A-Site', ''), ('B-Site', ''), ('a', 'Å'),
        ('Eᶠ|ABO₃', 'eV'), ('Eᶠ|Yᴮ', 'eV'), ('Eᶠ|Vᴼ', 'eV'),
        ('Eᶠ|Hᵢ', 'eV'), ('ΔEᵢ|Yᴮ-Hᵢ', 'eV')
    ]
    columns = df_dct.columns
    mpr = MPRester(endpoint="http://next.materialsproject.org/rest/v2")

    for row_idx, row in df_dct.iterrows():
        formula = '{}{}O3'.format(row[columns[0]], row[columns[1]])
        comp = Composition(formula)
        crit = {"reduced_cell_formula": comp.to_reduced_dict, "nsites": 5}
        docs = mpr.query(criteria=crit, properties=["task_id", "volume"])
        if len(docs) > 1:
            volume = row[columns[2]]**3
            volumes = pd.np.array([r['volume'] for r in docs])
            idx = pd.np.abs(volumes-volume).argmin()
            identifier = docs[idx]['task_id']
            continue
        elif not docs:
            print formula, 'not found on MP'
            continue
        else:
            identifier = docs[0]['task_id']
        print formula, '->', identifier
        d = RecursiveDict()
        for col, (key, unit) in zip(columns, columns_units):
            d[key] = clean_value(row[col], unit)
        mpfile.add_hierarchical_data(nest_dict(d, ['data']), identifier=identifier)
