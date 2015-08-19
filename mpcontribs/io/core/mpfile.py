from __future__ import unicode_literals, print_function
import six, codecs, locale
from abc import ABCMeta, abstractmethod, abstractproperty
from mpcontribs.config import mp_level01_titles

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
        elif not isinstance(filename_or_file, file):
            file_string = filename_or_file.read().decode('utf-8')
        else:
            file_string = filename_or_file.read()
        return cls.from_string(file_string)

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

    def __repr__(self): return self.get_string()
    def __str__(self): return self.get_string()

    # ----------------------------
    # Override these in subclasses
    # ----------------------------

    @abstractproperty
    def document(self):
        """internal data container/representation"""
        pass
    
    @abstractmethod
    def from_string(data):
        """Reads a MPFile from a string containing contribution data."""
        return MPFileCore()

    @abstractmethod
    def pop_first_section(self):
        """remove first root-level section and return as MPFile"""
        return MPFileCore()

    @abstractmethod
    def insert_general_section(self, general_mpfile):
        """insert general section from `general_mpfile` into this MPFile"""
        pass

    @abstractmethod
    def get_string(self):
        """Returns a string to be written as a file"""
        return 'empty file'

    def concat(self, mpfile):
        """concatenate single-section MPFile with this MPFile"""
        pass

    def insert_id(self, mp_cat_id, cid):
        """insert contribution ID for `mp_cat_id` as `cid: <cid>`"""
        pass

    def add_data_table(self, identifier, dataframe, name):
        """add a datatable to the root-level section

        Args:
            identifier (str): MP category ID (`mp_cat_id`)
            dataframe (pandas.DataFrame): tabular data as Pandas DataFrame
            name (str): table name, optional if only one table in section
        """
        pass
