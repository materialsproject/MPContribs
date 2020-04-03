# -*- coding: utf-8 -*-
from mpcontribs.io.core import mp_level01_titles
from mpcontribs.io.core.recdict import RecursiveDict
from IPython.display import display_html


class Structures(RecursiveDict):
    """class to hold and display list of pymatgen structures for single mp-id"""

    def __init__(self, content):
        from pymatgen import Structure

        super(Structures, self).__init__(
            (key, Structure.from_dict(struc))
            for key, struc in content.get(mp_level01_titles[3], {}).items()
        )

    def _ipython_display_(self):
        for name, structure in self.items():
            if structure:
                display_html("<h4>{}</h4>".format(name), raw=True)
                display_html(
                    "<p>{}</p>".format(
                        structure.__repr__()
                        .replace("\n", "<br>")
                        .replace(" ", "&nbsp;")
                    ),
                    raw=True,
                )


class StructuralData(RecursiveDict):
    """class to hold and display all pymatgen structures in MPFile"""

    def __init__(self, document):
        super(StructuralData, self).__init__(
            (identifier, Structures(content))
            for identifier, content in document.items()
        )

    def _ipython_display_(self):
        for identifier, sdata in self.items():
            if identifier != mp_level01_titles[0] and sdata:
                display_html(
                    "<h2>Structural Data for {}</h2>".format(identifier), raw=True
                )
                display_html(sdata)
