# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os, json, requests
from pandas import read_excel, isnull
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, hosts=None):
    mpfile.unique_mp_cat_ids = False
    from pymatgen import MPRester
    from unidecode import unidecode
    mpr = MPRester()
    figshare_id = mpfile.hdata.general['figshare_id']
    url = 'https://api.figshare.com/v2/articles/{}'.format(figshare_id)
    print 'get figshare article {}'.format(figshare_id)
    r = requests.get(url)
    figshare = json.loads(r.content)

    print 'load global/general meta-data from figshare'
    general = RecursiveDict()
    for k in ['title', 'description', 'doi', 'funding', 'version']:
        v = figshare[k]
        if k == 'description':
            v = ''.join([i if ord(i) < 128 else '' for i in v[3:-4]])
        if isinstance(v, str):
            v = unidecode(v.replace('\n', ' '))
        general[k] = unicode(v)
    general['authors'] = ', '.join([a['full_name'] for a in figshare['authors']])

    print 'read excel from figshare into DataFrame'
    df_dct = None
    for d in figshare['files']:
        if 'xlsx' in d['name']:
            # Dict of DataFrames is returned, with keys representing sheets
            df_dct = read_excel(d['download_url'], sheet_name=None)
            break
    if df_dct is None:
        print 'no excel sheet found on figshare'
        return

    print 'set index for host info, and add additional info'
    host_info = df_dct['Host Information']
    host_info.set_index(host_info.columns[0], inplace=True)
    add_info = 'Additional Information'
    general[add_info.lower()] = unidecode(
        ' '.join(host_info.loc[add_info:].dropna(axis=1).ix[:,0]).replace('  ', ' ')
    )
    mpfile.add_hierarchical_data(general)
    host_info.dropna(inplace=True)

    print 'looping hosts ...'
    for idx, host in enumerate(host_info):
        if hosts is not None:
            if isinstance(hosts, int) and idx+1 > hosts:
                break
            elif isinstance(hosts, list) and not host in hosts:
                continue

        print 'get mp-id for {}'.format(host)
        mpid = None
        for doc in mpr.query(
            criteria={'pretty_formula': host},
            properties={'task_id': 1}
        ):
            if doc['sbxd'][0]['decomposes_to'] is None:
                mpid = doc['task_id']
                break
        if mpid is None:
            print 'mp-id for {} not found'.format(host)
            continue

        print 'add host info for {}'.format(mpid)
        hdata = host_info[host].to_dict(into=RecursiveDict)
        for k in hdata.keys():
            v = hdata.pop(k)
            ks = k.split()
            if ks[0] not in hdata:
                hdata[ks[0]] = RecursiveDict()
            unit = ks[-1][1:-1] if ks[-1].startswith('[') else ''
            subkey = '_'.join(ks[1:-1] if unit else ks[1:]).split(',')[0]
            if subkey == "lattice_constant":
                unit = u'Å'
            try:
                hdata[ks[0]][subkey] = clean_value(v, unit.replace('angstrom', u'Å'))
            except ValueError:
                hdata[ks[0]][subkey] = v
        hdata['formula'] = host
        df = df_dct['{}-X'.format(host)]
        rows = list(isnull(df).any(1).nonzero()[0])
        if rows:
            cells = df.ix[rows].dropna(how='all').dropna(axis=1)[df.columns[0]]
            note = cells.iloc[0].replace('following', cells.iloc[1])[:-1]
            hdata['note'] = note
            df.drop(rows, inplace=True)
        mpfile.add_hierarchical_data(hdata, identifier=mpid)

        print 'add table for D0/Q data for {}'.format(mpid)
        df.set_index(df['Solute element number'], inplace=True)
        df.drop('Solute element number', axis=1, inplace=True)
        df.columns = df.ix[0]
        df.index.name = 'index'
        df.drop('Solute element name', inplace=True)
        df = df.T.reset_index()
        if str(host) == 'Fe':
            df_D0_Q = df[[
                'Solute element name', 'Solute D0, paramagnetic [cm^2/s]',
                'Solute Q, paramagnetic [eV]'
            ]]
        elif hdata['Host']['crystal_structure'] == 'HCP':
            df_D0_Q = df[['Solute element name', 'Solute D0 basal [cm^2/s]', 'Solute Q basal [eV]']]
        else:
            df_D0_Q = df[['Solute element name', 'Solute D0 [cm^2/s]', 'Solute Q [eV]']]
        df_D0_Q.columns = ['element', 'D0 [cm2/s]', 'Q [eV]']
        mpfile.add_data_table(mpid, df_D0_Q, 'D0_Q')

        if hdata['Host']['crystal_structure'] == 'BCC':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ['Hop activation barrier, E_{} [eV]'.format(i) for i in range(2,5)]+["Hop activation barrier, E'_{} [eV]".format(i) for i in range(3,5)]+["Hop activation barrier, E''_{} [eV]".format(i) for i in range(3,5)]+['Hop activation barrier, E_{} [eV]'.format(i) for i in range(5,7)]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ['E_{} [eV]'.format(i) for i in range(2,5)] + ["E'_{} [eV]".format(i) for i in range(3,5)] + ["E''_{} [eV]".format(i) for i in range(3,5)] + ['E_{} [eV]'.format(i) for i in range(5,7)]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(2,5)] + ["Hop attempt frequency, v'_{} [THz]".format(i) for i in range(3,5)] + ["Hop attempt frequency, v''_{} [THz]".format(i) for i in range(3,5)] + ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(5,7)]
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_{} [THz]'.format(i) for i in range(2,5)] + ["v''_{} [THz]".format(i) for i in range(3,5)] + ["v''_{} [THz]".format(i) for i in range(3,5)] + ['v_{} [THz]'.format(i) for i in range(5,7)]
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

        elif hdata['Host']['crystal_structure'] == 'FCC':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ['Hop activation barrier, E_{} [eV]'.format(i) for i in range(5)]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ['E_{} [eV]'.format(i) for i in range(5)]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_{} [THz]'.format(i) for i in range(5)]
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_{} [THz]'.format(i) for i in range(5)]
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

        elif hdata['Host']['crystal_structure'] == 'HCP':
            print 'add table for hop activation barriers for {}'.format(mpid)
            columns_E = ["Hop activation barrier, E_X [eV]","Hop activation barrier, E'_X [eV]","Hop activation barrier, E_a [eV]","Hop activation barrier, E'_a [eV]","Hop activation barrier, E_b [eV]","Hop activation barrier, E'_b [eV]","Hop activation barrier, E_c [eV]","Hop activation barrier, E'_c [eV]"]
            df_E = df[['Solute element name'] + columns_E]
            df_E.columns = ['element'] + ["E_X [eV]","E'_X [eV]","E_a [eV]","E'_a [eV]","E_b [eV]","E'_b [eV]","E_c [eV]","E'_c [eV]"]
            mpfile.add_data_table(mpid, df_E, 'hop_activation_barriers')
            print 'add table for hop attempt frequencies for {}'.format(mpid)
            columns_v = ['Hop attempt frequency, v_a [THz]'] + ['Hop attempt frequency, v_X [THz]']
            df_v = df[['Solute element name'] + columns_v]
            df_v.columns = ['element'] + ['v_a [THz]'] + ['v_X [THz]']
            mpfile.add_data_table(mpid, df_v, 'hop_attempt_frequencies')

    print 'DONE'
