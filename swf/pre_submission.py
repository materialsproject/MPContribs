from mpcontribs.users.swf.rest.rester import SWFRester
from mpcontribs.io.core.recdict import RecursiveDict
import pandas as pd
import pymatgen

def run(mpfile, nmax=None):
    df = pd.read_excel('~/work/MPContribs/mpcontribs/users/swf/swf_master_sheet.xlsx')
    df1 = df.iloc[:,0:4]; df1 = df1.dropna(how='all')
    df2 = df.iloc[:,5:8]
    df3 = df.iloc[:,9:14]; df3 = df3.dropna(how='all'); 
    df4 = df.iloc[:,15:20]; df4 = df4.dropna(how='all');
    df5 = df.iloc[:,21:27]; df5 = df5.dropna(how='all');

    df1 = df1.rename(index=str,columns={'IP Energy product (kJ/m3)': 'IP_Energy_product',
                'Fe (at%)': 'Fe', 'V (at%)': 'V', 'Co (at%)': 'Co'})
    df2 = df2.rename(index=str,columns={'Fe (tot)': 'Fe', 'V (tot)': 'V', 'Co (tot)': 'Co'})
    df3 = df3.rename(index=str,columns={'Fe (6c)': 'Fe', 'V (6c)': 'V', 'Co (6c)': 'Co', 'thickness (nm) (6c)': 'thickness',
                                       'MOKE IP Hc (Oe)': 'MOKE_IP_Hc'})
    df4 = df4.rename(index=str,columns={'Fe (6d)': 'Fe', 'V (6d)': 'V', 'Co (6d)': 'Co', 'thickness (nm) (6d)': 'thickness',
                                       'VSM IP Hc (Oe)': 'VSM_IP_Hc'})
    df5 = df5.rename(index=str,columns={'Fe (5a)': 'Fe', 'V (5a)': 'V', 'Co (5a)': 'Co', 'angle': 'angle',
                                       'Kondorsky Model (T)': 'Kondorsky_Model', 'Experiment (T)' : 'Experiment'})
    df_all = [df1, df2, df3, df4, df5]

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

    for i in range(len(df_all)):
        for index, row in df_all[i].iterrows():
            if pd.isnull(row['Fe']) == True:
                break
            row_replace = round_to_100_percent([row['Fe'], row['Co'], row['V']])
            row['Fe'] = row_replace[0]
            row['Co'] = row_replace[1]
            row['V'] = row_replace[2]
    
    comp5 = pymatgen.Composition(10*df5.iloc[0,0:3])
    formula5 = str(comp5).replace(' ', '')
    row5 = df5.iloc[0,0:3]; d5 = row5.to_dict(); 
    mpfile.add_hierarchical_data(d5, identifier=formula5)
    mpfile.add_data_table(formula5, df5.iloc[:,3:6], name='Angular Dependence of Switching Field')

    idx = 0
    df_allH = [df1, df2, df3, df4]
    for i in range(len(df_allH)):
        d = RecursiveDict()
        for index, row in df_allH[i].iterrows():
            d['Fe'] = row['Fe']*10
            d['V'] = row['V']*10
            d['Co'] = row['Co']*10
            comp = pymatgen.Composition(d)
            formula = str(comp).replace(' ', '')
            p = RecursiveDict()
            row_round = row.round(decimals=1)
            p = row_round.to_dict()
            mpfile.add_hierarchical_data(p, identifier=formula)
            if nmax is not None and idx >= nmax-1:
                    break
            idx += 1

    print(mpfile)