import os
import ase.db
import collections as coll
import urllib

def run(mpfile):
    url = mpfile.hdata['_hdata']['url']
    dbfile = url.rsplit('/')[-1]

    if not os.path.exists(dbfile):
        data = urllib.URLopener()
        data.retrieve(url, dbfile)

    con = ase.db.connect(dbfile)

    for idx, row in enumerate(con.select('mpid')):
        d = coll.OrderedDict([])
        d['kohn-sham_bandgap'] = coll.OrderedDict([])
        d['derivative_discontinuity'] = coll.OrderedDict([])
        d['quasi-particle_bandgap'] = coll.OrderedDict([])
        mpid = 'mp-' + str(row.mpid)
        d['kohn-sham_bandgap']['indirect'] = row.gllbsc_ind_gap - row.gllbsc_disc
        d['kohn-sham_bandgap']['direct'] = row.gllbsc_dir_gap - row.gllbsc_disc
        d['derivative_discontinuity'] = row.gllbsc_disc
        d['quasi-particle_bandgap']['indirect'] = row.gllbsc_ind_gap
        d['quasi-particle_bandgap']['direct'] = row.gllbsc_dir_gap
        mpfile.add_hierarchical_data(mpid,d)
        if idx == 10:
            break
