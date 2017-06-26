from __future__ import unicode_literals, print_function
import six, codecs, locale, pandas
from abc import ABCMeta
from mpcontribs.config import mp_level01_titles, default_mpfile_path
from recdict import RecursiveDict
from utils import pandas_to_dict, nest_dict
from components import HierarchicalData, TabularData, GraphicalData, StructuralData
from IPython.display import display_html
from pymatgen import Structure, MPRester

class MPFileCore(six.with_metaclass(ABCMeta, object)):
    """Abstract Base Class for representing a MP Contribution File"""
    def __init__(self, data=RecursiveDict()):
        if isinstance(data, dict):
            self.document = RecursiveDict(data)
        else:
            raise ValueError('Need dict (or inherited class) to init MPFile.')
        self.document.rec_update() # convert (most) OrderedDict's to RecursiveDict's

    def __getitem__(self, key):
        item = self.from_dict({key: self.document[key]})
        general = self.document.get(mp_level01_titles[0])
        if general:
            item.insert_general_section(self.from_dict({mp_level01_titles[0]: general}))
        return item

    @property
    def ids(self):
        return [
            k for k in self.document.keys()
            if k.lower() != mp_level01_titles[0]
        ]

    @property
    def hdata(self):
        return HierarchicalData(self.document)

    @property
    def tdata(self):
        return TabularData(self.document)

    @property
    def gdata(self):
        return GraphicalData(self.document)

    @property
    def sdata(self):
        return StructuralData(self.document)

    @classmethod
    def from_file(cls, filename_or_file=default_mpfile_path.replace('.txt', '_in.txt')):
        """Reads a MPFile from a file.

        Args:
            filename_or_file (str or file): name of file or file containing contribution data.

        Returns:
            MPFile object.
        """
        if isinstance(filename_or_file, six.string_types):
            lang, encoding = locale.getdefaultlocale()
            file_string = codecs.open(filename_or_file, encoding=encoding).read()
        else:
            file_string = filename_or_file.read()
        return cls.from_string(file_string)

    @classmethod
    def from_dict(cls, data=RecursiveDict()):
        return cls(data=data)

    @classmethod
    def from_contribution(cls, contrib):
        """construct MPFile from contribution (see rest.adapter.submit_contribution)"""
        if not 'mp_cat_id' in contrib or not 'content' in contrib:
            raise ValueError('Dict not in contribution-style format')
        recdict = RecursiveDict({contrib['mp_cat_id']: contrib['content']})
        return cls.from_dict(recdict)

    def write_file(self, filename=default_mpfile_path.replace('.txt', '_out.txt'), **kwargs):
        """Writes MPFile to a file. The supported kwargs are the same as those
        for the MPFile.get_string method and are passed through directly."""
        with codecs.open(filename, encoding='utf-8', mode='w') as f:
            file_str = self.get_string(**kwargs) + '\n'
            f.write(file_str)

    def get_number_of_lines(self, **kwargs):
        return len(self.get_string(**kwargs).split('\n'))

    def split(self):
        general_mpfile = self.pop_first_section() \
                if mp_level01_titles[0] in self.document.keys() else None
        if not self.document:
            raise ValueError('No contributions in MPFile! Either the file is'
                             ' empty or only contains shared (meta-)data not'
                             ' correlated to core identifier.')
        while True:
            try:
                mpfile_single = self.pop_first_section()
                if general_mpfile is not None:
                    mpfile_single.insert_general_section(general_mpfile)
                yield mpfile_single
            except KeyError:
                break

    def get_identifiers(self):
        """list of materials/composition identifiers as tuples w/ contribution IDs"""
        return [
            (k, self.document[k].get('cid', None))
            for k in self.document
            if k.lower() != mp_level01_titles[0]
        ]

    def pop_first_section(self):
        return self.from_dict(RecursiveDict([
            self.document.popitem(last=False)
        ]))

    def insert_general_section(self, general_mpfile):
        """insert general section from `general_mpfile` into this MPFile"""
        if general_mpfile is None: return
        general_title = mp_level01_titles[0]
        general_data = general_mpfile.document[general_title]
        root_key = self.document.keys()[0]
        first_subkey = self.document[root_key].keys()[0]
        for key, value in general_data.items():
            if key in self.document[root_key]:
                self.document.rec_update(nest_dict(value, [root_key, key]))
            else:
                self.document[root_key].insert_before(first_subkey, (key, value))

    def concat(self, mpfile, uniquify=True):
        """concatenate single-section MPFile with this MPFile"""
        try:
            if len(mpfile.document) > 1:
                raise ValueError('concatenation only possible with single section files')
        except AttributeError:
            raise ValueError('Provide a MPFile to concatenate')
        mp_cat_id = mpfile.document.keys()[0]
        general_title = mp_level01_titles[0]
        if general_title in mpfile.document[mp_cat_id]:
            general_data = mpfile.document[mp_cat_id].pop(general_title)
            if general_title not in self.document:
                self.document.rec_update(nest_dict(general_data, [general_title]))
        mp_cat_id_idx, mp_cat_id_uniq = 0, mp_cat_id
        if uniquify:
            while mp_cat_id_uniq in self.document.keys():
                mp_cat_id_uniq = mp_cat_id + '--{}'.format(mp_cat_id_idx)
                mp_cat_id_idx += 1
        self.document.rec_update(nest_dict(
            mpfile.document.pop(mp_cat_id), [mp_cat_id_uniq]
        ))

    def insert_id(self, mp_cat_id, cid):
        """insert contribution ID for `mp_cat_id` as `cid: <cid>`"""
        if len(self.document) > 1:
            raise ValueError('ID insertion only possible for single section files')
        first_sub_key = self.document[mp_cat_id].keys()[0]
        self.document[mp_cat_id].insert_before(first_sub_key, ('cid', str(cid)))

    def add_data_table(self, identifier, dataframe, name):
        """add a datatable to the root-level section

        Args:
            identifier (str): MP category ID (`mp_cat_id`)
            dataframe (pandas.DataFrame): tabular data as Pandas DataFrame
            name (str): table name, optional if only one table in section
        """
        # TODO: optional table name, required if multiple tables per root-level section
        table_start = mp_level01_titles[1]+'_'
        if not name.startswith(table_start):
            name = table_start + name
        self.document.rec_update(nest_dict(
            pandas_to_dict(dataframe), [identifier, name]
        ))

    def add_hierarchical_data(self, identifier, dct):
        self.document.rec_update(nest_dict(dct, [identifier]))

    def add_structure(self, source, name=None, identifier=None, fmt=None):
        """add a structure to the mpfile"""
        if isinstance(source, Structure):
            structure = source
        elif isinstance(source, dict):
            structure = Structure.from_dict(source)
        elif os.path.exists(source):
            structure = Structure.from_file(source, sort=True)
        elif isinstance(source, six.string_types):
            if fmt is None:
                raise ValueError('Need fmt to get structure from string!')
            structure = Structure.from_str(source, fmt, sort=True)
        else:
            raise ValueError(source, 'not supported!')

        mpr = MPRester()
        if not mpr.api_key:
            raise ValueError(
                'API key not set. Run `pmg config --add PMG_MAPI_KEY <USER_API_KEY>`.'
            )
        matched_mpids = mpr.find_structure(structure)
        if not matched_mpids:
            raise ValueError(
                'Structure not found in MP. Please submit via MPComplete to obtain mp-id!'
            )
        elif identifier is None:
            identifier = matched_mpids[0]
            if len(matched_mpids) > 1:
                print('Multiple matching structures found in MP. Using', identifier)
        elif identifier not in matched_mpids:
            raise ValueError('Structure does not match {} but instead {}'.format(
                identifier, matched_mpids
            ))

        idx = len(self.document.get(identifier, {}).get(mp_level01_titles[3], {}))
        sub_key = 's{}'.format(idx) if name is None else name
        self.document.rec_update(nest_dict(
            structure.as_dict(), [identifier, mp_level01_titles[3], sub_key]
        ))

    def __repr__(self): return self.get_string()
    def __str__(self): return self.get_string()

    def _ipython_display_(self):
        display_html(self.hdata)
        display_html(self.tdata)
        display_html(self.gdata)

    # ----------------------------
    # Override these in subclasses
    # ----------------------------

    def from_string(data):
        """Reads a MPFile from a string containing contribution data."""
        return MPFileCore()

    def get_string(self):
        """Returns a string to be written as a file"""
        return 'empty file'
