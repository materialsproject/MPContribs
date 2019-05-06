from IPython.display import display_html
from mpcontribs.config import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict

class HierarchicalData(RecursiveDict):
    """class to hold and display all hierarchical data in MPFile"""
    def __init__(self, doc):
        super(HierarchicalData, self).__init__(
            (k, v) for k, v in doc.items() if k not in mp_level01_titles
        )
