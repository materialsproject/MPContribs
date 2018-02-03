# -*- coding: utf-8 -*-
import os, tarfile, json, re, urllib, certifi
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from monty.json import MontyDecoder
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile):

    for typ in ['2d', '3d']:

        url = mpfile.hdata.general['input_url'].format(typ)
        dbfile = os.path.join(os.environ['HOME'], 'work', url.rsplit('/')[-1])

        if not os.path.exists(dbfile):
            print 'downloading', dbfile, '...'
            urllib.urlretrieve(url, dbfile)
            #resp = urlrq.urlopen('https://foo.com/bar/baz.html', cafile=certifi.where())

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

            print 'DONE with', typ
