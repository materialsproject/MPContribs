from IPython.display import display_html
from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.utils import nest_dict
from mpcontribs.io.core.recdict import RecursiveDict

class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""
    def __init__(self, document):
        from pymatgen import Structure
        super(HierarchicalData, self).__init__()
        scope = []
        for key, value in document.iterate():
            if isinstance(value, Table) or isinstance(value, Structure):
                continue
            level, key = key
            level_reduction = bool(level < len(scope))
            if level_reduction:
                del scope[level:]
            if value is None:
                scope.append(key)
            elif mp_level01_titles[2] not in scope:
                self.rec_update(nest_dict({key: value}, scope))

    @property
    def general(self):
        return self[mp_level01_titles[0]]

    def __str__(self):
        return 'mp-ids: {}'.format(' '.join(self.keys()))

    def _ipython_display_(self):
        display_html('<h2>Hierarchical Data</h2>', raw=True)
        for identifier, hdata in self.items():
            if identifier != mp_level01_titles[0]:
                display_html('<h3>{}</h3>'.format(identifier), raw=True)
            display_html(hdata)
