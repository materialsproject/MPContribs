import requests, six
from pandas import read_excel, notnull
import numpy as np
from unidecode import unidecode
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.config import mp_level01_titles
from mpcontribs.users.dibbs.rest.rester import DibbsRester

def run(mpfile, nmax=None, dup_check_test_site=True):

    existing_mpids = {}
    for b in [False, True]:
        with DibbsRester(test_site=b) as mpr:
            for doc in mpr.query_contributions(criteria=mpr.dibbs_query):
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    general = mpfile.document[mp_level01_titles[0]]
    input_file = general.pop('input_file')
    df = read_excel(input_file)
    columns_map = RecursiveDict([
        (v, k) for k, v in general.pop('columns_map').items()
    ])
    columns = columns_map.keys()
    df = df[columns]
    df = df[notnull(df[columns[-1]]) & notnull(df[columns[1]])]
    mpfile.add_hierarchical_data({'title': 'DIBBS - 27Al NMR'})

    count, skipped, update = 0, 0, 0
    for idx, row in df.iterrows():
        url = row[columns[-1]]
        if not url.startswith('http'):
            continue

        # hierarchical data
        d = RecursiveDict()
        for col in columns[:4]:
            d[columns_map[col]] = unidecode(row[col]) \
                    if isinstance(row[col], six.string_types) else row[col]

        if d['name'] in [
            'AlPO4 Tridymite (AlPO4-t)', 'Basic aluminum sulfate', 'Cryolite',
            'berlinite(AlPO4-Q)'
        ]:
            continue

        d['data'] = RecursiveDict()
        for col in columns[4:8]:
            if notnull(row[col]):
                value = unicode('{}'.format(row[col]), 'utf-8')
                if col == columns[4]:
                    value += ' ppm'
                elif col == columns[6]:
                    value += ' MHz'
                elif col == columns[7]:
                    value = ' '.join([value[:-1], value[-1]])
            else:
                value = u''
            d['data'][columns_map[col]] = value

        # structure
        if url.startswith('https://materialsproject.org'):
            mpid = url.split('/')[-2]
        else:
            #print 'retrieve cif and match to MP structure ...'
            d[columns_map[columns[-1]]] = url
            f = requests.get(url)

            try:
                mpid = mpfile.add_structure(f.text, name=d['name'], fmt='cif')
            except ValueError as ex:
                print d['name'], str(ex)
                continue

            if nmax is not None and mpid in existing_mpids:
                item = mpfile.document.popitem(last=True)
                print 'removed duplicate', mpid

        if nmax is not None and mpid in existing_mpids:
            print 'skipping', mpid
            skipped += 1
            continue # skip duplicates

        mpfile.add_hierarchical_data(d, identifier=mpid)
        print 'added {} ({})'.format(d['name'], mpid)

        if mpid in existing_mpids:
            cid = existing_mpids[mpid]
            mpfile.insert_id(mpid, cid)
            update += 1
        if nmax is not None and count >= nmax-1:
            break
        count += 1

    print len(mpfile.ids), 'mp-ids to submit.'
    if nmax is None and update > 0:
        print update, 'mp-ids to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'
