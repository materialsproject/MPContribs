from __future__ import unicode_literals, print_function
import six, pandas, warnings
from mpcontribs.config import mp_level01_titles
from ..core.mpfile import MPFileCore
from ..core.recdict import RecursiveDict
from ..core.utils import pandas_to_dict, nest_dict
from collections import OrderedDict
from recparse import RecursiveParser
from utils import make_pair, get_indentor

class MPFile(MPFileCore):
    """Object for representing a MP Contribution File in a custom format."""

    @staticmethod
    def from_string(data):
        # strip comments from data string
        lines, comments = [], OrderedDict()
        for idx,line in enumerate(data.splitlines()):
            idx_str, line = str(idx), line
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
        mpfile = MPFile.from_dict(parser.document)
        mpfile.comments = comments
        return mpfile

    @classmethod
    def from_dict(cls, data=RecursiveDict()):
        mpfile = super(MPFile, cls).from_dict(data)
        mpfile.comments = OrderedDict()
        return mpfile

    def add_comment(self, linenumber, comment):
        """add comment to line <linenumber>. An asterisk appended to
        <linenumber> denotes a comment on its own line"""
        self.comments[linenumber] = comment

    def shift_comment(self, idx_str, shift):
        comment = self.comments.pop(idx_str)
        idx_str_shift = self.get_shifted_comment_index(idx_str, shift)
        self.comments[idx_str_shift] = comment

    def shift_comments(self, shift):
        linenumbers = self.comments.keys()
        if shift > 0: linenumbers.reverse()
        for idx_str in linenumbers:
            self.shift_comment(idx_str, shift)

    def get_comment_index(self, idx_str):
        try:
            idx, ast = int(idx_str), False
        except:
            idx, ast = int(idx_str[:-1]), True
        return idx, ast

    def get_shifted_comment_index(self, idx_str, shift):
        idx, ast = self.get_comment_index(idx_str)
        idx += shift
        return str(idx) + ('*' if ast else '')

    def pop_first_section(self):
        mpfile = super(MPFile, self).pop_first_section()
        nlines = mpfile.get_number_of_lines(with_comments=True)
        for idx_str in self.comments.keys():
            idx = self.get_comment_index(idx_str)[0]
            if idx < nlines:
                comment = self.comments.pop(idx_str)
                mpfile.add_comment(idx_str, comment)
            else:
                self.shift_comment(idx_str, -nlines)
        return mpfile

    # 2015-08-21: insert_general_section is deprecated. Comments needed to be
    # switched off due to the missing +1 shift if "shared" or "data" keys are
    # inserted during parsing. Also, nlines_top is no longer correct /
    # calculated after the switch to treating all non-identifier root level keys
    # as "shared (meta-)data".
    #def insert_general_section(self, general_mpfile):
    #    # FIXME rec_update will probably not play nice with comments
    #    nlines_top = super(MPFile, self).insert_general_section(general_mpfile)
    #    general_nlines = general_mpfile.get_number_of_lines(with_comments=False)
    #    for idx_str in reversed(self.comments.keys()):
    #        idx = self.get_comment_index(idx_str)[0]
    #        if idx < 1: continue
    #        self.shift_comment(idx_str, general_nlines-1)
    #    for idx_str in reversed(general_mpfile.comments.keys()):
    #        idx_str_shift = self.get_shifted_comment_index(idx_str, nlines_top)
    #        self.add_comment(idx_str_shift, general_mpfile.comments[idx_str])

    def concat(self, mpfile):
        super(MPFile, self).concat(mpfile) 
        # TODO: account for comments
        if mpfile.comments:
            warnings.warn('NotImplementedError: comments ignored in concatenation!')
        #shift = mpfile.get_number_of_lines(with_comments=True)
        #for idx_str in mpfile.comments.keys():
        #    idx_str_shift = mpfile.get_shifted_comment_index(idx_str, shift)
        #    self.add_comment(idx_str_shift, mpfile.comments[idx_str])

    def insert_id(self, mp_cat_id, cid):
        super(MPFile, self).insert_id(mp_cat_id, cid)
        self.shift_comments(1)

    def get_string(self, with_comments=False):
        lines = []
        min_indentor = get_indentor()
        table_start = mp_level01_titles[1]+' '
        for key,value in self.document.iterate():
            if key is None and isinstance(value, pandas.DataFrame):
                csv_string = value.to_csv(index=False, float_format='%g')[:-1]
                lines += csv_string.split('\n')
            else:
                key = get_indentor(n=key) if isinstance(key, int) else key
                sep = '' if min_indentor in key else ':'
                if lines and key == min_indentor:
                    lines.append('')
                if isinstance(value, six.string_types):
                    if value.startswith(table_start):
                        value = value[len(table_start):]
                    if ':' in value: # quote to ignore delimiter
                        value = '"{}"'.format(value)
                lines.append(make_pair(key, value, sep=sep))
        if with_comments:
            for idx_str, comment in self.comments.iteritems():
                idx, ast = self.get_comment_index(idx_str)
                if ast: lines.insert(idx, '#'+comment)
                else: lines[idx] = ' #'.join([lines[idx], comment])
        return '\n'.join(lines) + '\n'

MPFileCore.register(MPFile)
