from __future__ import unicode_literals, print_function
import six, codecs, locale
from abc import ABCMeta, abstractmethod, abstractproperty
from mpcontribs.config import mp_level01_titles
from recdict import RecursiveDict
from utils import pandas_to_dict, nest_dict

class MPFileCore(six.with_metaclass(ABCMeta, object)):
    """Abstract Base Class for representing a MP Contribution File"""

    @classmethod
    def from_file(cls, filename_or_file):
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
        if not isinstance(data, RecursiveDict):
            raise ValueError('Need RecursiveDict to init MPFile.')
        mpfile = cls()
        mpfile.document = data
        mpfile.document.rec_update() # convert (most) OrderedDict's to RecursiveDict's
        return mpfile

    def write_file(self, filename, **kwargs):
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
        # need to reverse-loop to keep the order of the general_mpfile
        for key, value in reversed(general_data.items()):
            if key in self.document[root_key]:
                self.document.rec_update(nest_dict(value, [root_key, key]))
            else:
                # this approach is due to the order sensitivity of key-value pairs
                # before or after a `>>>..` row in the custom format (legacy)
                # => ignoring it here would generate the wrong MPFile in get_string
                for k,v in self.document[root_key].iteritems():
                    if isinstance(v, dict):
                        self.document[root_key].insert_before(k, (key, value))
                        break

    def concat(self, mpfile):
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
        self.document.rec_update(nest_dict(
            pandas_to_dict(dataframe), [identifier, name]
        ))

    def __repr__(self): return self.get_string()
    def __str__(self): return self.get_string()

    # ----------------------------
    # Override these in subclasses
    # ----------------------------

    def from_string(data):
        """Reads a MPFile from a string containing contribution data."""
        return MPFileCore()

    def get_string(self):
        """Returns a string to be written as a file"""
        return 'empty file'
