import os
#from mpcontribs.users.dtu.rest.rester import DtuRester

def run(mpfile, nmax=None, dup_check_test_site=True):

    #existing_mpids = {}
    #for b in [False, True]:
    #    with DtuRester(test_site=b) as mpr:
    #        for doc in mpr.query_contributions(criteria=mpr.dtu_query):
    #            existing_mpids[doc['mp_cat_id']] = doc['_id']
    #    if not dup_check_test_site:
    #        break

    input_dir = mpfile.hdata.general['input_dir']
    print input_dir
