import os
import ase.db
from collections import OrderedDict

def run(mpfile):
    url = mpfile.hdata['_hdata']['url']
    # TODO
    # - extract db name from url -> dbfile = 'mp_gllbsc.db'
    # - check if mp_gllbsc.db exists
    # - if not, download using python code instead of wget
    dbfile = 'mp_gllbsc.db'
    if os.path.exists(dbfile):
        print 'file exists'
    else:
        print 'need to download'

    con = ase.db.connect(dbfile)
    for row in con.select('mpid'):
        d = OrderedDict()
        mpid = 'mp-' + str(row.mpid)
        d['band_gap'] = 0.5
        mpfile.add_hierarchical_data(mpid, d)
        print 'added hierarchical data for', mpid
        break
    print mpfile

