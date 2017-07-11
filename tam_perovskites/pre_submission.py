from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.config import mp_level01_titles
from pandas import read_excel
from six import string_types


def run(mpfile):

    descriptors_filepath = mpfile.document[mp_level01_titles[0]].pop('descriptors_filepath')
    contcars_filepath = mpfile.document[mp_level01_titles[0]].pop('contcars_filepath') # TODO
    df = read_excel(descriptors_filepath)
    df = df[df['Materials project match id'] != ' None '].reset_index() # skip un-matched
    keys = df.iloc[[0]].to_dict(orient='records')[0]
    abbreviations = RecursiveDict()

    for index, row in df[1:].iterrows():
        mpid = None
        data = RecursiveDict()

        for col, value in row.iteritems():
            if col == 'level_0' or col == 'index':
                continue
            key = keys[col]
            if isinstance(key, string_types):
                key = key.strip()
                if not key in abbreviations:
                    abbreviations[key] = col
            else:
                key = col.strip().lower()

            if key == 'pmgmatchid':
                mpid = value.strip()
            else:
                data[key] = value

        mpfile.add_hierarchical_data(data, identifier=mpid)
        print 'added', mpid
        if index > 5:
            break

    mpfile.add_hierarchical_data({'abbreviations': abbreviations})
    print 'DONE'
