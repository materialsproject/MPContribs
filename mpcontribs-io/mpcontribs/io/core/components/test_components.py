# -*- coding: utf-8 -*-
import os
import json
from mpcontribs.io.core import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.components.hdata import HierarchicalData
from mpcontribs.io.core.components.tdata import Table
from mpcontribs.io.core.components.gdata import Plot


def test_components():
    d = {k: {} for k in mp_level01_titles}
    d["data"] = {"a": 3.5, "b": {"display": "6 eV", "value": 6, "unit": "eV"}}
    exp = HierarchicalData([("data", RecursiveDict([("a", 3.5), ("b", "6 eV")]))])
    assert HierarchicalData(d) == exp

    fn = os.path.join(os.path.dirname(__file__), "test_table.json")
    with open(fn, "r") as f:
        d = json.load(f)
        table = Table.from_dict(d)
        assert table.render()
        plot = Plot.from_dict(d)
        assert plot.get_figure()
