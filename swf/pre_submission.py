from mpcontribs.config import mp_level01_titles
from mpcontribs.users.swf.rest.rester import SwfRester
from mpcontribs.io.core.recdict import RecursiveDict
import pandas as pd

def round_to_100_percent(number_set, digit_after_decimal=1):
    unround_numbers = [
        x / float(sum(number_set)) * 100 * 10**digit_after_decimal
        for x in number_set
    ]
    decimal_part_with_index = sorted([
        (index, unround_numbers[index] % 1)
        for index in range(len(unround_numbers))
    ], key=lambda y: y[1], reverse=True)
    remainder = 100 * 10**digit_after_decimal - sum(map(int, unround_numbers))
    index = 0
    while remainder > 0:
        unround_numbers[decimal_part_with_index[index][0]] += 1
        remainder -= 1
        index = (index + 1) % len(number_set)
    return [int(x)/float(10**digit_after_decimal) for x in unround_numbers]

def run(mpfile, nmax=None, dup_check_test_site=True):
    import pymatgen

    existing_compositions = {}
    for b in [False, True]:
        with SwfRester(test_site=b) as mpr:
            for doc in mpr.query_contributions():
                existing_compositions[doc['mp_cat_id']] = doc['_id']
        if not dup_check_test_site:
            break

    # load data from google sheet
    # TODO should google sheets URL be removed from contribution?
    google_sheet = mpfile.document[mp_level01_titles[0]].pop('google_sheet')
    google_sheet += '/export?format=xlsx'
    df_dct = pd.read_excel(google_sheet, sheetname=None)

    # rename sheet columns
    elements = ['Fe', 'V', 'Co']
    df_dct['IP Energy Product'].columns = ['IP_Energy_product'] + elements
    df_dct['total'].columns = elements
    df_dct['MOKE'].columns = elements + ['thickness', 'MOKE_IP_Hc']
    df_dct['VSM'].columns = elements + ['thickness', 'VSM_IP_Hc']
    df_dct['formula'].columns = elements
    df_dct['Kondorsky'].columns = ['angle', 'Kondorsky_Model', 'Experiment']

    # round all compositions to 100%
    for sheet, df in df_dct.items():
        if sheet != 'Kondorsky':
            for idx, row in df.iterrows():
                df.loc[idx:idx, elements] = round_to_100_percent(row[elements])

    row5 = df_dct['formula'].iloc[0]
    formula5 = pymatgen.Composition(10*row5).formula.replace(' ', '')
    if nmax is not None and formula5 in existing_compositions:
        print 'skipping kondorsky for', formula5
    else:
        mpfile.add_hierarchical_data(
            {'data': row5.to_dict()}, identifier=formula5
        )
        mpfile.add_data_table(
            formula5, df_dct['Kondorsky'], name='Angular Dependence of Switching Field'
        )

    count, skipped, update = 0, 0, 0
    for sheet, df in df_dct.items():
        if sheet == 'formula' or sheet == 'Kondorsky' or sheet == 'total':
            continue
        for idx, row in df.iterrows():
            composition = pymatgen.Composition(row[elements]*10)
            formula = composition.formula.replace(' ', '')
            if nmax is not None and formula in existing_compositions:
                print 'skipping', formula
                skipped += 1
                continue # skip duplicates

            mpfile.add_hierarchical_data(
                {'data': row[elements].to_dict()},
                identifier=formula
            )

            columns = [x for x in row.index if x not in elements]
            if columns:
                data = row[columns].round(decimals=1)
                mpfile.add_hierarchical_data(
                    {'data': data.to_dict()}, identifier=formula
                )

            if formula in existing_compositions:
                cid = existing_compositions[formula]
                mpfile.insert_id(formula, cid)
                update += 1
            if nmax is not None and count >= nmax-1:
                    break
            count += 1

    print len(mpfile.ids), 'compositions to submit.'
    if nmax is None and update > 0:
        print update, 'compositions to update.'
    if nmax is not None and skipped > 0:
        print skipped, 'duplicates to skip.'
