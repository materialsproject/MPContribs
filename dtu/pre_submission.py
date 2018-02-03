# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, urllib, ase.db
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):

    url = mpfile.hdata.general['input_url']
    dbfile = os.path.join(os.environ['HOME'], 'work', url.rsplit('/')[-1])

    if not os.path.exists(dbfile):
        data = urllib.URLopener()
        data.retrieve(url, dbfile)

    con = ase.db.connect(dbfile)
    nr_mpids = con.count(selection='mpid')

    for idx, row in enumerate(con.select('mpid')):
        if idx and not idx%10:
            print 'added', idx, '/', nr_mpids, 'materials'

        mpid = 'mp-' + str(row.mpid)
        d = RecursiveDict()
        d['formula'] = row.formula
        d['ICSD'] = str(row.icsd_id)
        d['data'] = RecursiveDict()
        # kohn-sham band gap
        d['data']['ΔE-KS'] = RecursiveDict([
            ('indirect', clean_value(
                row.gllbsc_ind_gap - row.gllbsc_disc, 'eV'
            )), ('direct', clean_value(
                row.gllbsc_dir_gap - row.gllbsc_disc, 'eV'
            ))
        ])
        # quasi particle band gap
        d['data']['ΔE-QP'] = RecursiveDict([
            ('indirect', clean_value(row.gllbsc_ind_gap, 'eV')),
            ('direct', clean_value(row.gllbsc_dir_gap, 'eV'))
        ])
        # derivative discontinuity
        d['data']['C'] = clean_value(row.gllbsc_disc, 'eV')

        mpfile.add_hierarchical_data(d, identifier=mpid)
