import os
import json
from pymatgen import MPRester
from pymatgen.core.periodic_table import Element

data = {}
elements = [e for e in Element]
print('save formulae for', len(elements), 'elements ...')

with MPRester() as mpr:
    for element in elements:
        print(element)
        mids = mpr.get_materials_ids(element)
        docs = mpr.query(criteria={"task_id": {'$in': mids}}, properties=["task_id", "pretty_formula"])
        for d in docs:
            data[d['task_id']] = d['pretty_formula']
        print(len(docs), 'task ids for', element)

out = os.path.join(os.path.dirname(__file__), 'formulae.json')
with open(out, 'w') as f:
    json.dump(data, f)
