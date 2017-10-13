#from mpcontribs.users.dlr_vieten.rest.rester import DlrVietenRester
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from mpcontribs.io.core.utils import get_composition_from_string
from mpcontribs.io.core.recdict import RecursiveDict
import pandas as pd
import csv

def run(mpfile, dup_check_test_site=True):

    from pymatgen import MPRester
    existing_identifiers = {}
    #for b in [False, True]:
    #    with DlrVietenRester(test_site=b) as mpr:
    #        for doc in mpr.query_contributions():
    #            existing_identifiers[doc['mp_cat_id']] = doc['_id']
    #    if not dup_check_test_site:
    #        break

    google_sheet = mpfile.document[mp_level01_titles[0]].pop('google_sheet')
    google_sheet += '/export?format=xlsx'
    df_dct = pd.read_excel(google_sheet, sheetname=None)
    ionic_radii_hdata = mpfile.document[mp_level01_titles[0]].pop('ionic_radii')

    mpr = MPRester()
    update = 0
    for sheet in df_dct.keys():
        print(sheet)
        df = df_dct[sheet]

        if sheet == 'ionic radii':
            for idx, row in df.iterrows():
                if idx>5:
                    break

                element = row['species']
                print 'ionic radii for', element
                docs = mpr.query(
                    criteria={
                        'pretty_formula': element,
                        'decomposes_to': None,
                    }, properties={'task_id': 1}
                )
                if len(docs) == 1:
                    identifier = mpfile.get_unique_mp_cat_id(docs[0]['task_id'])
                    d = RecursiveDict(ionic_radii_hdata)
                    d.rec_update({'data': row.to_dict()})
                    mpfile.add_hierarchical_data(
                        {'ionic_radii': d}, identifier=identifier
                    )
                elif not docs:
                    print element, 'not found!'
                    continue
                else:
                    print len(docs), 'mp-ids found for', element
                    continue


        else:
            sheet_split = sheet.split()
            composition = sheet_split[0]
            identifier = get_composition_from_string(composition)
            if len(sheet_split) > 1 and mp_id_pattern.match(sheet_split[1]):
                identifier = sheet_split[1]
            print('identifier = {}'.format(identifier))

            if 'CIF' in sheet_split:
                print('adding CIF ...')
                df.columns = [df.columns[0]] + ['']*(df.shape[1]-1)
                cif = df.to_csv(na_rep='', index=False, sep='\t', quoting=csv.QUOTE_NONE)
                mpfile.add_structure(cif, identifier=identifier, fmt='cif')

            else:
                print('adding data ...')
                mpfile.add_hierarchical_data({'composition': composition}, identifier=identifier)
                mpfile.add_data_table(identifier, df, name='dH_dS')

        if identifier in existing_identifiers:
            cid = existing_identifiers[identifier]
            mpfile.insert_id(identifier, cid)
            update += 1

    print len(mpfile.ids), 'contributions to submit.'
    if update > 0:
        print update, 'contributions to update.'


