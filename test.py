#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json
chunks = map(StringIO, open('test.csv','r').read().split('\n#>>>\n'))
nSets = len(chunks)
# options on how to read the table
options = [
    { 'index_col': 0, 'header': None },
    {},
    {'index_col': 0},
    {}
]
# orientation for translation into JSON:
# Series: split, records, index
# DataFrame: Series + columns, values
orients = [ 'index', 'records', 'index', 'values' ]
for i,chunk in enumerate(chunks):
    df = pd.read_csv(
        chunk, skiprows=1, comment='#', skipinitialspace=True,
        squeeze=True, **options[i]
    )
    print df
    parsed = json.loads(df.to_json(orient=orients[i]))
    print json.dumps(parsed, indent=2, sort_keys=True)
