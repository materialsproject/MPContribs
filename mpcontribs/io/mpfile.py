import os, json, six
from abc import ABCMeta
from utils import make_pair, get_indentor, RecursiveDict, nest_dict, pandas_to_dict
from ..config import mp_level01_titles
from recparse import RecursiveParser
from monty.io import zopen
from pandas import DataFrame
from six import string_types
from collections import OrderedDict

class MPFile(six.with_metaclass(ABCMeta)):
    """Object for representing a MP Contribution File.

    Args:
        parser (RecursiveParser): recursive parser object, init empty RecursiveDict() if None
    """
    def __init__(self, parser=None):
        self.comments = OrderedDict()
        self.document = RecursiveDict() if parser is None else parser.document

    @staticmethod
    def from_file(filename_or_file):
        """Reads a MPFile from a file.

        Args:
            filename_or_file (str or file): name of file or file containing contribution data.

        Returns:
            MPFile object.
        """
        if isinstance(filename_or_file, string_types):
            filename_or_file = zopen(filename_or_file, "rt")
        return MPFile.from_string(filename_or_file.read())

    @staticmethod
    def from_string(data):
        """Reads a MPFile from a string.

        Args:
            data (str): String containing contribution data.

        Returns:
            MPFile object.
        """
        # strip comments from data string
        lines, comments = [], OrderedDict()
        for idx,line in enumerate(data.splitlines()):
            idx_str, line = str(idx), line.encode('utf-8')
            line_split = line.lstrip().split('#', 1)
            lines.append(line_split[0])
            if len(line_split) > 1:
                if not line_split[0]: idx_str += '*'
                comments[idx_str] = line_split[1]
        data = '\n'.join(lines)
        # parse remaining data string
        parser = RecursiveParser()
        parser.parse(data)
        # init MPFile
        mpfile = MPFile(parser)
        mpfile.set_comments(comments)
        return mpfile

    @staticmethod
    def from_dict(mp_cat_id, data):
        mpfile = MPFile()
        mpfile.document.rec_update(nest_dict(data, [mp_cat_id]))
        return mpfile

    def set_comments(self, comments):
        """comments = {linenumber: comment}, see `add_comment`"""
        self.comments = comments

    def add_comment(self, linenumber, comment):
        """add comment to line <linenumber>. An asterisk appended to
        <linenumber> denotes a comment on its own line"""
        self.comments[linenumber] = comment

    def apply_general_section(self):
        """apply general level-0 section on all other level-0 sections"""
        # TODO prepend not append to contribution
        general_title = mp_level01_titles[0]
        if general_title in self.document:
            general_data = self.document.pop(general_title)
            for k in self.document:
                self.document[k].rec_update({general_title: general_data})

    def get_string(self):
        """Returns a string to be written as a file"""
        lines = []
        min_indentor = get_indentor()
        for key,value in self.document.iterate():
            if key is None and isinstance(value, DataFrame):
                csv_string = value.to_csv(index=False, float_format='%g')[:-1]
                lines += csv_string.split('\n')
            else:
                sep = '' if min_indentor in key else ':'
                if lines and key == min_indentor:
                    lines.append('')
                lines.append(make_pair(key, value, sep=sep))
        return '\n'.join(lines).decode('utf-8')

    def __repr__(self):
        return self.get_string()

    def __str__(self):
        """String representation of MPFile file."""
        return self.get_string()

    def write_file(self, filename, **kwargs):
        """Writes MPFile to a file. The supported kwargs are the same as those
        for the MPFile.get_string method and are passed through directly."""
        with zopen(filename, "wt") as f:
            f.write(self.get_string(**kwargs))

    def add_data_table(self, identifier, dataframe, name):
        """add a data table/frame to the root-level section for identifier"""
        # TODO: optional table name, required if multiple tables per root-level section
        self.document.rec_update(nest_dict(
            pandas_to_dict(dataframe), [identifier, name]
        ))

    def get_identifiers(self):
        """list of identifiers (i.e. all root-level headers excl. GENERAL"""
        return [ k for k in self.document if k.lower() != mp_level01_titles[0] ]
