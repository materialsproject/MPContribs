#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json
chunks = map(StringIO, open('test.csv','r').read().split('\n#>>>\n'))
nSets = len(chunks)
options = [
    { 'index_col': 0, 'header': None },
    {},
] + [ {} ] * (nSets-2)
orients = [
    'index', 'records',
] + [ '' ] * (nSets-2)
for i,chunk in enumerate(chunks):
    if i > 1: break
    df = pd.read_csv(
        chunk, skiprows=1, comment='#', skipinitialspace=True,
        squeeze=True, **options[i]
    )
    print df
    parsed = json.loads(df.to_json(orient=orients[i]))
    print json.dumps(parsed, indent=2, sort_keys=True)
