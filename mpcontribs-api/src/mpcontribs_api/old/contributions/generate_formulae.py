# -*- coding: utf-8 -*-
import os
import json
from pymatgen.ext.matproj import MPRester

data = {}

with MPRester() as mpr:
    for i, d in enumerate(
        mpr.query(criteria={}, properties=["task_ids", "pretty_formula"])
    ):
        for task_id in d["task_ids"]:
            data[task_id] = d["pretty_formula"]

out = os.path.join(os.path.dirname(__file__), "formulae.json")
with open(out, "w") as f:
    json.dump(data, f)
