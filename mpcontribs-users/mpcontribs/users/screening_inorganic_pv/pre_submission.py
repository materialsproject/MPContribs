# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, json
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):

    infile = mpfile.hdata.general['input']['summary']
    data = json.load(open(infile, 'r'))
    config = RecursiveDict([
        ('SLME_500_nm', ['SLME|500nm', '%']),
        ('SLME_1000_nm', ['SLME|1000nm', '%']),
        ('E_g', ['ΔE##corrected', 'eV']),
        ('E_g_d', ['ΔE##direct', 'eV']),
        ('E_g_da', ['ΔE##dipole-allowed', 'eV']),
        ('m_e', ['mₑ', 'mₑ']),
        ('m_h', ['mₕ', 'mₑ'])
    ])


    for mp_id, d in data.iteritems():
        print mp_id
        rd = RecursiveDict()
        for k, v in config.items():
            value = clean_value(d[k], v[1])
            if not '##' in v[0]:
                rd[v[0]] = value
            else:
                keys = v[0].split('##')
                if not keys[0] in rd:
                    rd[keys[0]] = RecursiveDict({keys[1]: value})
                else:
                    rd[keys[0]][keys[1]] = value

        mpfile.add_hierarchical_data({'data': rd}, identifier=mp_id)
