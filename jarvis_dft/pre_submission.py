# -*- coding: utf-8 -*-
import os, tarfile, json, re, urllib
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from monty.json import MontyDecoder
from mpcontribs.users.jarvis_dft.rest.rester import JarvisDftRester

def clean_value(val, unit):
    return '-' if val == 'na' else '{} {}'.format(val, unit)

def run(mpfile, nmax=10, dup_check_test_site=True):

    # book-keeping
    existing_mpids = {}
    for b in [False, True]:
        with JarvisDftRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.query):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    for typ in ['2d', '3d']:

        url = mpfile.hdata['_hdata']['input_url'].format(typ)
        dbfile = url.rsplit('/')[-1]

        if not os.path.exists(dbfile):
            print 'downloading', dbfile, '...'
            url_opener = urllib.URLopener()
            url_opener.retrieve(url, dbfile)

        else:
            print 'unpacking', dbfile, '...'
            with tarfile.open(dbfile, "r:gz") as tar:
                member = tar.getmembers()[0]
                d = json.load(tar.extractfile(member), cls=MontyDecoder)
                print len(d), 'materials loaded.'

                for idx,i in enumerate(d):
                    mpid = i['mpid']
                    print 'adding', mpid, '...'
                    data = RecursiveDict()
                    data['jid'] = i['jid']
                    data['formula'] = i['final_str'].composition.reduced_formula
                    data['spacegroup'] = i['final_str'].get_space_group_info()[0]
                    data['final_energy'] = clean_value(i["fin_en"], 'eV')
                    data['optB88vDW_bandgap'] = clean_value(i["op_gap"], 'eV')
                    data['mbj_bandgap'] = clean_value(i["mbj_gap"], 'eV')
                    data['bulk_modulus'] = clean_value(i["kv"], 'GPa')
                    data['shear_modulus'] = clean_value(i["gv"], 'GPa')
                    mpfile.add_hierarchical_data(nest_dict(data, ['data', typ]), identifier=mpid)
                    mpfile.add_structure(i['final_str'], name=data['formula'], identifier=mpid)

                    if mpid in existing_mpids:
                        cid = existing_mpids[mpid]
                        mpfile.insert_id(mpid, cid)
                        print cid, 'inserted to update', mpid

                    if idx >= nmax-1:
                        break

            print 'DONE with', typ
