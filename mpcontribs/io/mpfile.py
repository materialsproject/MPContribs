import os, json, six
from abc import ABCMeta
from utils import make_pair, get_indentor
from recparse import RecursiveParser
from monty.io import zopen
from pandas import DataFrame

class MPFile(six.with_metaclass(ABCMeta)):
    """Object for representing a MP Contribution File.

    Args:
        parser (RecursiveParser): recursive parser object
    """
    def __init__(self, parser):
        self.document = parser.document

    @staticmethod
    def from_file(filename):
        """Reads a MPFile from a file.

        Args:
            filename (str): name of file containing contribution data.

        Returns:
            MPFile object.
        """
        fileExt = os.path.splitext(filename)[1][1:]
        with zopen(filename, "rt") as f:
            return MPFile.from_string(f.read(), fileExt)

    @staticmethod
    def from_string(data, fileExt):
        """Reads a MPFile from a string.

        Args:
            data (str): String containing contribution data.
            fileExt (str): file extension (csv or tsv) to define tabular data format

        Returns:
            MPFile object.
        """
        data = '\n'.join([ # remove all comment lines first
            line for line in data.splitlines()
            if not line.lstrip().startswith("#")
        ])
        parser = RecursiveParser(fileExt)
        parser.parse(data)
        return MPFile(parser)

    def get_string(self):
        """Returns a string to be written as a file"""
        lines = []
        min_indentor = get_indentor()
        for key,value in self.document.iterate():
            if key is None and isinstance(value, DataFrame):
                lines.append(value.to_csv(index=False, float_format='%g')[:-1])
            else:
                sep = '' if min_indentor in key else ':'
                if key == min_indentor: lines.append('')
                lines.append(make_pair(key, value, sep=sep))
        return '\n'.join(lines)

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
