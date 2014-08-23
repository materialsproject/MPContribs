#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'

# read data
chunks = map(StringIO, open('input.csv','r').read().split('\n#>>>\n'))
nSets = len(chunks)

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
sections = None
doc = {}
for i,chunk in enumerate(chunks):
    # import data table
    df = pd.read_csv(
        chunk, skiprows=1, comment='#', skipinitialspace=True,
        squeeze=True, **options[i]
    )
    if i < 1:
        sections = df.values.tolist()
    else:
        print df
        df_json = df.to_json(orient=orients[i])
        sec_json = '{"'+sections[i-1]+'":'+df_json+'}'
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
