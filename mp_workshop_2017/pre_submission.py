from mpcontribs.users.mp_workshop_2017.rest.rester import MpWorkshop2017Rester
from mpcontribs.config import mp_level01_titles
import pandas as pd

def run(mpfile, mpids=[], nmax=None, dup_check_test_site=True):

    if not mpids:
        print 'To continue, set mpids=[...] as argument in run()!'
        return

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

    hdata_prov = ['reference', 'subtitle', 'author', 'description']
    hdata_mp = ['identifier'] + hdata_prov
    hdata_col_headers = [x for x in df_dct['main'].columns if x not in hdata_mp]

    tables = dict(
        tuple(sheet.split('__')) for sheet in df_dct.keys() if sheet != 'main'
    )

    count, skipped, update = 0, 0, 0
    for idx, row in df_dct['main'].iterrows():
        row.dropna(inplace=True)
        if 'identifier' not in row:
            continue
        mpid = row['identifier']
        if mpid not in mpids:
            continue

        if nmax is not None and mpid in existing_mpids:
            print 'skipping', mpid
            skipped += 1
            continue # skip duplicates

        mpfile.add_hierarchical_data(row[hdata_prov].to_dict(), identifier=mpid)
        mpfile.add_hierarchical_data(
            {'data': row[hdata_col_headers].to_dict()}, identifier=mpid
        )

        if mpid in tables:
            sheet = '__'.join([mpid, tables[mpid]])
            mpfile.add_data_table(mpid, df_dct[sheet], name=tables[mpid])

        if mpid in existing_mpids:
            cid = existing_mpids[mpid]
            mpfile.insert_id(mpid, cid)
            update += 1

        if nmax is not None and count >= nmax-1:
            break
        count += 1

    print len(mpfile.ids), 'mpids to submit.'
    if nmax is None and update > 0:
        print update, 'mpids to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'


