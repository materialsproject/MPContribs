# -*- coding: utf-8 -*-
import os, urllib, ase.db
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from mpcontribs.users.utils import clean_value, duplicate_check

@duplicate_check
def run(mpfile, **kwargs):

    url = mpfile.hdata['_hdata']['url']
    dbfile = url.rsplit('/')[-1]

    if not os.path.exists(dbfile):
        data = urllib.URLopener()
        data.retrieve(url, dbfile)

    con = ase.db.connect(dbfile)

    for idx, row in enumerate(con.select('mpid')):
        mpid = 'mp-' + str(row.mpid)
        if mpid not in run.existing_identifiers:
            continue

        d = RecursiveDict()

        # kohn-sham band gap
        d['ΔE-KS'] = RecursiveDict([
            ('indirect', clean_value(
                row.gllbsc_ind_gap - row.gllbsc_disc, 'eV'
            )), ('direct', clean_value(
                row.gllbsc_dir_gap - row.gllbsc_disc, 'eV'
            ))
        ])

        # derivative discontinuity
        d['C'] = clean_value(row.gllbsc_disc, 'eV')

        # quasi particle band gap
        d['ΔE-QP'] = RecursiveDict([
            ('indirect', clean_value(row.gllbsc_ind_gap, 'eV')),
            ('direct', clean_value(row.gllbsc_dir_gap, 'eV'))
        ])

        mpfile.add_hierarchical_data(
            nest_dict(d, ['data']), identifier=mpid
        )
