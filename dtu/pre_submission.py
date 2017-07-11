import os
import ase.db
import urllib
from mpcontribs.users.dtu.rest.rester import DtuRester
from mpcontribs.io.core.recdict import RecursiveDict

def run(mpfile, nmax=None, dup_check_test_site=True):

    existing_mpids = {}
    for b in [False, True]:
        with DtuRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.dtu_query):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    url = mpfile.hdata['_hdata']['url']
    dbfile = url.rsplit('/')[-1]

    if not os.path.exists(dbfile):
        data = urllib.URLopener()
        data.retrieve(url, dbfile)

    con = ase.db.connect(dbfile)

    idx, skipped, update = 0, 0, 0
    for row in con.select('mpid'):
        mpid = 'mp-' + str(row.mpid)
        if nmax is not None and mpid in existing_mpids:
            skipped += 1
            continue # skip duplicates
        d = RecursiveDict()
        d['kohn-sham_bandgap'] = RecursiveDict()
        d['derivative_discontinuity'] = RecursiveDict()
        d['quasi-particle_bandgap'] = RecursiveDict()
        d['kohn-sham_bandgap']['indirect'] = row.gllbsc_ind_gap - row.gllbsc_disc
        d['kohn-sham_bandgap']['direct'] = row.gllbsc_dir_gap - row.gllbsc_disc
        d['derivative_discontinuity'] = row.gllbsc_disc
        d['quasi-particle_bandgap']['indirect'] = row.gllbsc_ind_gap
        d['quasi-particle_bandgap']['direct'] = row.gllbsc_dir_gap
        mpfile.add_hierarchical_data(d, identifier=mpid)
        if mpid in existing_mpids:
            cid = existing_mpids[mpid]
            mpfile.insert_id(mpid, cid)
            update += 1
        if nmax is not None and idx >= nmax-1:
            break
        idx += 1

    print len(mpfile.ids), 'mp-ids to submit.'
    if nmax is None and update > 0:
        print update, 'mp-ids to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'
