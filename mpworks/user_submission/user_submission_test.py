#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json, sys, re, string
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'

# data import
filestr = open('input.csv','r').read()
section_separator_regex = r'>{4,}(.*)\n'
chunks = filter(
  len, # remove 0-length strings
  re.split(section_separator_regex, filestr) # split into section chunks
)
section_names = map(
  string.strip, # strip leading and trailing spaces
  [ # strip in-line comments and lower-case
    re.split(r'#*', s)[0].lower() for s in chunks[::2]
  ] # even entries in chunks contain separator lines
)
sections = map(StringIO, chunks[1::2])
print section_names
sys.exit(0)

# options on how to read the table
# http://pandas.pydata.org/pandas-docs/dev/io.html#csv-text-files
options = [
    { 'header': None },
    { 'index_col': 0, 'header': None },
    {}, {'index_col': 0}, {}
]

# orientation for translation into JSON:
# Series: split, records, index
# DataFrame: Series + columns, values
# http://pandas.pydata.org/pandas-docs/dev/io.html#writing-json
orients = [ 'values', 'index', 'records', 'columns', 'values' ]

# plot options
# http://pandas.pydata.org/pandas-docs/stable/visualization.html
# table=True
plotopts = [
    {}, {},
    { 'x': 'name', 'kind': 'bar' },
    { 'table': True },
    { 'x': 'freq' }
]

# iterate data chunks
doc = {}
for i,chunk in enumerate(chunks):
    # import data table
    df = pd.read_csv(
        chunk, skiprows=1, comment='#', skipinitialspace=True,
        squeeze=True, **options[i]
    )
    print df
    df_json = df.to_json(orient=orients[i])
    sec_json = '{"'+section_names[i-1]+'":'+df_json+'}'
    doc.update(json.loads(sec_json))
    continue
    # plot (possibly replace with plot.ly)
    fig, ax = plt.subplots(1, 1)
    if i == 2: ax.get_xaxis().set_visible(False)
    df.plot(ax=ax, **plotopts[i])
    plt.savefig('png/fig%d' % i, dpi=300, bbox_inches='tight')

json.dump(
    doc, open('output.json','wb'), indent=2, sort_keys=True
)
