import os
import json
from pymatgen import MPRester

data = {}

with MPRester() as mpr:
    for i, d in enumerate(mpr.query(criteria={}, properties=["task_id", "pretty_formula"])):
        data[d['task_id']] = d['pretty_formula']

out = os.path.join(os.path.dirname(__file__), 'formulae.json')
with open(out, 'w') as f:
    json.dump(data, f)
