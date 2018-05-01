# -*- coding: utf-8 -*-
import os, tarfile, json, re, urllib, certifi
import numpy as np
from pandas import DataFrame
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from monty.json import MontyDecoder
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.utils import clean_value
import gzip
import ast

@duplicate_check
def run(mpfile, **kwargs):

    url_2d_J = mpfile.hdata.general['jarvis2d_url']
    url_3d_J = mpfile.hdata.general['jarvis3d_url']
    url_2D = mpfile.hdata.general['2D_sample_url']
    urls = [url_2d_J, url_3d_J, url_2D]
    typs = ['2d_J','3d_J', '2D']
    d = RecursiveDict()
    for typ in typs:
        idx = typs.index(typ)
        dbfile = os.path.join(os.environ['HOME'], 'work', urls[idx].rsplit('/')[-1])

        if not os.path.exists(dbfile):
            print 'downloading', dbfile, '...'
            urllib.urlretrieve(url, dbfile)
            #resp = urlrq.urlopen('https://foo.com/bar/baz.html', cafile=certifi.where())

        else:
            if typ is not '2D':
                print 'unpacking', dbfile, '...'
                with tarfile.open(dbfile, "r:gz") as tar:
                    member = tar.getmembers()[0]
                    d[typ] = json.load(tar.extractfile(member), cls=MontyDecoder)
                    print len(d[typ]), 'materials loaded.'

            else:
                print 'unpacking', dbfile, '...'
                d[typ] = []
                with gzip.open(dbfile, 'rb') as f:
                    for line in f:
                        d[typ].append(json.loads(line))
                    print len(d[typ]), 'materials loaded.'

    mpid_query = list()
    for j in range(0,len(d['2D'])):
        mpid_query.append(d['2D'][j]['parent_id']) 

    keys_all = RecursiveDict()
    keys_all['2d_J'] = ['mpid','jid', 'final_str', 'exfoliation_en', 'fin_en', 'final_str']
    keys_all['3d_J'] = ['mpid','jid', 'final_str', 'fin_en', 'final_str']
    keys_all['2D'] = ['parent_id','material_id','formula_pretty','exfoliation_energy_per_atom','structure']

    for typ in typs:
        keys = keys_all[typ]
        D = d[typ]
        for idx,i in enumerate(D):
            mpid = i[keys[0]]
            data = RecursiveDict()
            data['source_detail_page'] = i[keys[1]]
            if typ is '2d_J':
                data['formula'] = i[keys[2]].composition.reduced_formula
                data['exfoliation_energy'] = clean_value(i[keys[3]], 'meV')
                data['final_energy'] = clean_value(i[keys[4]], 'meV')
            elif typ is '3d_J':
                data['formula'] = i[keys[2]].composition.reduced_formula
                data['exfoliation_energy'] = 'na'
                data['final_energy'] = clean_value(i[keys[3]], 'meV')
            else:
                data['formula'] = i[keys[2]]
                data['exfoliation_energy'] = clean_value(i[keys[3]], 'eV')
                data['final_energy'] = 'na'
            if mpid in mpid_query:
                print 'adding', mpid, 'of type', typ, '...'
                mpfile.add_hierarchical_data(nest_dict(data, ['data', typ]), identifier=mpid)
                mpfile.add_structure(i[keys[-1]], name=data['formula'], identifier=mpid)

