# -*- coding: utf-8 -*-
from mpcontribs.io.core import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict


class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""

    def __init__(self, doc):
        super(HierarchicalData, self).__init__()
        document = RecursiveDict(doc)
        scope = []
        for key, value in document.iterate():
            level, key = key
            if key in mp_level01_titles:
                continue
            level_reduction = bool(level < len(scope))
            if level_reduction:
                del scope[level:]
            if value is None:
                scope.append(key)
            else:
                d = nest_dict(value, scope + [key])
                self.rec_update(d, overwrite=True)
