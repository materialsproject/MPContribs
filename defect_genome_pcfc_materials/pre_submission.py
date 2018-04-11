# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.users.utils import duplicate_check
from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
import pandas as pd
from mpcontribs.io.core.utils import clean_value
from mpcontribs.io.core.utils import get_composition_from_string

@duplicate_check
def run(mpfile, **kwargs):
    import pymatgen
    
    df_dct = pd.read_excel('DefectGenome_JPCC-data_MP.xlsx')
    headers = list(df_dct)
   
    mpfile.max_contribs = 100
    for row in df_dct.iterrows():
        d = RecursiveDict()
        for idx in range(len(headers)):
            d[headers[idx]] = clean_value(row[1][headers[idx]])
        composition = get_composition_from_string(str(row[1][headers[0]]) + str(row[1][headers[1]]))
        mpfile.add_hierarchical_data(d, identifier = composition)
    