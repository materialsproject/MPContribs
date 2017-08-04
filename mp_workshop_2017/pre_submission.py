from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.users.mpworkshop17.rest.rester import MpWorkshop2017Rester
import pandas as pd
from mpcontribs.config import mp_level01_titles

def run(mpfile, nmax=None, dup_check_test_site=True):

    existing_mpids = {}
    for b in [False, True]:
        with MpWorkshop2017Rester(test_site=b) as mpr:
            for doc in mpr.query_contributions():
                existing_mpids[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    google_sheet = mpfile.document[mp_level01_titles[0]].pop('google_sheet')
    google_sheet += '/export?format=xlsx'
    df_dct = pd.read_excel(google_sheet, sheetname=None)

    hdata_prov = ['reference','title','author','description']
    hdata_mp = ['identifier','reference','title','author','description']
    hdata_col_headers = filter(lambda x: x not in hdata_prov, df_dct['main'].columns.values)
    table_headers = []
    for sheet, df in df_dct.items():
        if sheet != 'main':
            table_headers.append(str(sheet))

    print(existing_mpids)

    count, skipped, update = 0, 0, 0
    for idx, row in df_dct['main'].iterrows():
        mpid = row['identifier']
        if nmax is not None and mpid in existing_mpids:
            print 'skipping', mpid
            skipped += 1
            continue # skip duplicates
        if mpid in existing_mpids:
            cid = existing_mpids[mpid]
            mpfile.insert_id(mpid, cid)
            update += 1
        if nmax is not None and count >= nmax-1:
            break
        count += 1

        data = RecursiveDict()
        mpfile.add_hierarchical_data(row[hdata_prov].to_dict(), identifier = mpid)
        for index in range(len(hdata_col_headers)/2):
            if pd.isnull(row['x{}_key'.format(index)]):
                break
            data[row['x{}_key'.format(index)]] = row['x{}_value'.format(index)]
            mpfile.add_hierarchical_data({'data': data}, identifier = mpid)

    for idx in range(len(table_headers)):
        mpfile.add_data_table(table_headers[idx].split('__')[0],df_dct[table_headers[idx]], name= table_headers[idx].split('__')[1])

    print len(mpfile.ids), 'mpids to submit.'
    if nmax is None and update > 0:
        print update, 'mpids to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'


