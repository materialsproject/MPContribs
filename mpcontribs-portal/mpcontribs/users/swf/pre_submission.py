from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import clean_value, get_composition_from_string
from mpcontribs.users.utils import duplicate_check

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

@duplicate_check
def run(mpfile, **kwargs):
    import pymatgen
    import pandas as pd
    from mpcontribs.users.swf.rest.rester import SwfRester

    # load data from google sheet
    google_sheet = mpfile.document[mp_level01_titles[0]].pop('google_sheet')
    google_sheet += '/export?format=xlsx'
    df_dct = pd.read_excel(google_sheet, sheet_name=None)

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
    formula5 = get_composition_from_string(
        pymatgen.Composition(10*row5).formula.replace(' ', '')
    )
    dct = dict((k, clean_value(v, '%')) for k,v in row5.to_dict().items())
    mpfile.add_hierarchical_data({'data': dct}, identifier=formula5)
    mpfile.add_data_table(
        formula5, df_dct['Kondorsky'], name='Angular Dependence of Switching Field'
    )

    for sheet, df in df_dct.items():
        if sheet == 'formula' or sheet == 'Kondorsky' or sheet == 'total':
            continue
        for idx, row in df.iterrows():
            composition = pymatgen.Composition(row[elements]*10)
            formula = get_composition_from_string(composition.formula.replace(' ', ''))
            dct = dict((k, clean_value(v, '%')) for k,v in row[elements].to_dict().items())
            mpfile.add_hierarchical_data({'data': dct}, identifier=formula)
            columns = [x for x in row.index if x not in elements]
            if columns:
                data = row[columns].round(decimals=1)
                dct = dict((k, clean_value(v)) for k,v in data.to_dict().items())
                mpfile.add_hierarchical_data({'data': dct}, identifier=formula)

