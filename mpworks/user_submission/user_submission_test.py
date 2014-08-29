#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json, sys, re, string
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'

# (sub-)section separator regex'es
section_separator_regex = r'\n*>{4,}(.+)\n*'
subsection_separator_regex = r'\n*>{2,3}(.+)\n*'

options = [
    { 'header': None },
    { 'index_col': 0, 'header': None },
    {}, {'index_col': 0}, {}
]
orients = [ 'values', 'index', 'records', 'columns', 'values' ]
plotopts = [
    {}, {},
    { 'x': 'name', 'kind': 'bar' },
    { 'table': True },
    { 'x': 'freq' }
]

def clean_title(title):
    """strip in-line comments & spaces, make lower-case"""
    return re.split(r'#*', title)[0].strip().lower()

def read_csv(s, **options):
    """run pandas.read_csv on string"""
    return pd.read_csv(
        StringIO(s), comment='#', skipinitialspace=True, squeeze=True, **options
    )

def json_rep():
    pass

# read input file,
# split into section title line (even) and section body (odd entries)
# see https://docs.python.org/2/library/re.html#re.split for leading empty string
filestr = open('input.csv','r').read()
sections = re.split(section_separator_regex, filestr)[1:]

# iterate sections
doc = {}
for section_index,section_body in enumerate(sections[1::2]):
    section_title = clean_title(sections[2*section_index])
    subsections = re.split(subsection_separator_regex, section_body)
    number_subsections = len(subsections)
    # all sections can have optional subsections named 'general', 'plot' & 'data'
    if number_subsections == 1: # no subsections (only data) or 'general'-section
        read_csv_options = {
            'sep': ':' if section_title == 'general' else ',',
            'header': None if section_title == 'general' else 0,
            'index_col': 0,
        }
        df = read_csv(subsections[0], **read_csv_options)
        print '%s:\n%r' % (section_title, df)
        continue
    continue
    subsections = subsections[1:] # dirty fix to omit leading empty string
    for subsection_index,subsection_body in enumerate(subsections[1::2]):
        subsection_title = clean_title(subsections[2*subsection_index])
        df = read_csv(subsection_body, sep = ',' if subsection_title == 'data' else ':')
        print '%s > %s: %s' % (section_title, subsection_title, df.to_json())
    continue
    # import data table
    df_json = df.to_json(orient=orients[i])
    sec_json = '{"'+section_titles[i-1]+'":'+df_json+'}'
    doc.update(json.loads(sec_json))
    # plot (possibly replace with plot.ly)
    fig, ax = plt.subplots(1, 1)
    if i == 2: ax.get_xaxis().set_visible(False)
    df.plot(ax=ax, **plotopts[i])
    plt.savefig('png/fig%d' % i, dpi=300, bbox_inches='tight')

json.dump(
    doc, open('output.json','wb'), indent=2, sort_keys=True
)
