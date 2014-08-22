#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'

# read data
chunks = map(StringIO, open('test.csv','r').read().split('\n#>>>\n'))
nSets = len(chunks)

# options on how to read the table
# http://pandas.pydata.org/pandas-docs/dev/io.html#csv-text-files
options = [
    { 'index_col': 0, 'header': None },
    {}, {'index_col': 0}, {}
]

# orientation for translation into JSON:
# Series: split, records, index
# DataFrame: Series + columns, values
# http://pandas.pydata.org/pandas-docs/dev/io.html#writing-json
orients = [ 'index', 'records', 'columns', 'values' ]

# plot options
# http://pandas.pydata.org/pandas-docs/stable/visualization.html
# table=True
plotopts = [
    {},
    { 'x': 'name', 'kind': 'bar' },
    { 'table': True },
    { 'x': 'freq' }
]

# iterate data chunks
for i,chunk in enumerate(chunks):
    # import data table
    df = pd.read_csv(
        chunk, skiprows=1, comment='#', skipinitialspace=True,
        squeeze=True, **options[i]
    )
    print df
    # parse json
    parsed = json.loads(df.to_json(orient=orients[i]))
    print json.dumps(parsed, indent=2, sort_keys=True)
    # plot (possibly replace with plot.ly)
    if i > 0:
        fig, ax = plt.subplots(1, 1)
        if i == 2: ax.get_xaxis().set_visible(False)
        df.plot(ax=ax, **plotopts[i])
        plt.savefig('fig%d' % i, dpi=300, bbox_inches='tight')
