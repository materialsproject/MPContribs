#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json, sys, re, string
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'
section_separator_regex = r'\n*>{4,}(.+)\n*'
subsection_separator_regex = r'\n*>{2,3}(.+)\n*'

def clean_title(title):
    """strip in-line comments & spaces, make lower-case"""
    return re.split(r'#*', title)[0].strip().lower()

def read_csv(s, **options):
    """run pandas.read_csv on string"""
    return pd.read_csv(
        StringIO(s), comment='#', skipinitialspace=True, squeeze=True, **options
    )

def import_csv(filename):
    """import MP-formatted csv file into MP database"""
    # read input file,
    # split into section title line (even) and section body (odd entries)
    # see https://docs.python.org/2/library/re.html#re.split for leading empty string
    filestr = open(filename,'r').read()
    sections = re.split(section_separator_regex, filestr)[1:]
    # iterate sections
    doc = {}
    for section_index,section_body in enumerate(sections[1::2]):
        section_title = clean_title(sections[2*section_index])
        subsections = re.split(subsection_separator_regex, section_body)
        # 'general'-section or section with no subsections (only data)
        if len(subsections) == 1:
            read_csv_options = {
                'sep': ':' if section_title == 'general' else ',',
                'header': None if section_title == 'general' else 0,
                'index_col': 0,
            }
            df = read_csv(subsections[0], **read_csv_options)
            to_json_options = {
                'orient': 'index' if section_title == 'general' else 'columns',
            }
            df_json = df.to_json(**to_json_options)
            doc_json = '{"%s":%s}' % (section_title, df_json)
            doc.update(json.loads(doc_json))
            continue
        # section with subsections 'general' or 'plot' or 'data'
        subsections = subsections[1:] # dirty fix to omit leading empty string
        user_orient = None
        for subsection_index,subsection_body in enumerate(subsections[1::2]):
            subsection_title = clean_title(subsections[2*subsection_index])
            read_csv_options = { 'sep': ',' }
            if subsection_title != 'data':
                read_csv_options = { 'sep': ':', 'index_col': 0, 'header': None }
            df = read_csv(subsection_body, **read_csv_options)
            if subsection_title == 'general' and 'orient' in df.index:
                user_orient = df.orient
            df_json = df.to_json(
                orient = 'index' if (
                    subsection_title != 'data' or user_orient is None
                ) else user_orient
            )
            doc_json = '{"%s":{"%s":%s}}' % (section_title, subsection_title, df_json)
            doc.update(json.loads(doc_json))
    json.dump(doc, open('output.json','wb'), indent=2, sort_keys=True)

def plot(filename):
    """plot all data based on output.json (-> plot.ly in future?)"""
    pass
    #fig, ax = plt.subplots(1, 1)
    #if Table: ax.get_xaxis().set_visible(False)
    #df.plot(ax=ax, **plotopts[i])
    #plt.savefig('png/fig%d' % i, dpi=300, bbox_inches='tight')

if __name__ == '__main__':
    import_csv('input.csv')
    plot('output.json')
