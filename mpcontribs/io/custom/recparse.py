from __future__ import unicode_literals, print_function
import re, logging
import numpy as np
import pandas as pd
from StringIO import StringIO
from mpcontribs.config import indent_symbol, csv_comment_char, mp_level01_titles, mp_id_pattern
from utils import get_indentor
from ..core.recdict import nest_dict, RecursiveDict, pandas_to_dict
from collections import OrderedDict
from mpcontribs.pymatgen_utils.composition import Composition

class RecursiveParser():
    def __init__(self):
        """init and set read_csv options"""
        self.level0_counter = 0
        self.section_titles = []
        self.document = RecursiveDict({})
        self.level = -1 # level counter
        self.data_options = { 'sep': ',', 'header': 0 }
        self.colon_key_value_list = { 'sep': ':', 'header': None, 'index_col': 0 }

    def separator_regex(self):
        """get separator regex for section depth/level"""
        # (?:  ) => non-capturing group
        # (?:^|\n+) => match beginning of string OR one or more newlines
        # %s\s+ => match next-level separator followed by one or more spaces
        #    require minimum one space after section level identifier
        # (.+) => capturing group of one or more arbitrary characters
        # (?:$|\n*?) => match end-of-string OR zero or more newlines
        #    be non-greedy with newlines at end of string
        return r'(?:^|\n+)%s\s+(.+)(?:$|\n*?)' % get_indentor(self.level+1)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case if mp-id"""
        title = re.split(
            r'%s*' % csv_comment_char, title
        )[0].strip()
        if self.level+1 == 0:
          is_mp_id = mp_id_pattern.match(title)
          title_lower = title.lower()
          if is_mp_id or title_lower == mp_level01_titles[0]:
            return title_lower
          else:
            return Composition(title).get_integer_formula_and_factor()[0]
        return title

    def is_bare_section(self, title):
        """determine whether currently in bare section"""
        return (title != mp_level01_titles[0] and self.level == 0)

    def is_data_section(self, body):
        """determine whether currently in data section"""
        return (get_indentor() not in body and ':' not in body)

    def strip(self, text):
        """http://stackoverflow.com/questions/13385860"""
        if not text:
            return np.nan
        try:
            return float(text)
        except ValueError:
            try:
                return text.strip()
            except AttributeError:
                return text

    def read_csv(self, title, body):
        """run pandas.read_csv on (sub)section body"""
        if not body: return False, None
        is_data_section = self.is_data_section(body)
        if is_data_section:
            options = self.data_options
            cur_line = 1
            while 1:
                first_line = body.split('\n', cur_line)[cur_line-1]
                cur_line += 1
                if not first_line.strip().startswith(csv_comment_char):
                    break
            ncols = len(first_line.split(options['sep']))
        else:
            options = self.colon_key_value_list
            ncols = 2
        converters = dict((col,self.strip) for col in range(ncols))
        return is_data_section, pd.read_csv(
            StringIO(body), comment=csv_comment_char,
            skipinitialspace=True, squeeze=True,
            converters=converters, encoding='utf8',
            **options
        ).dropna(how='all')

    def increase_level(self, next_title):
        """increase and prepare for next section level"""
        self.section_titles.append(next_title)
        logging.info(self.section_titles)
        self.level += 1

    def reduce_level(self):
        """reduce section level"""
        self.section_titles.pop()
        self.level -= 1

    def parse(self, file_string):
        """recursively parse sections according to number of separators"""
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            # check for preceding bare section_body (without section title), and parse
            if sections[0]: self.parse(sections[0])
            # drop preceding bare section_body
            sections = sections[1:] # https://docs.python.org/2/library/re.html#re.split
            for section_index,section_body in enumerate(sections[1::2]):
                clean_title = self.clean_title(sections[2*section_index])
                # uniquify level-0 titles if necessary
                if self.level+1 == 0 and clean_title in self.document:
                    clean_title += '--%d' % self.level0_counter
                    self.level0_counter += 1
                self.increase_level(clean_title)
                self.parse(section_body)
                self.reduce_level()
        else:
            # separator level not found, convert section body to pandas object,
            section_title = self.section_titles[-1]
            is_data_section, pd_obj = self.read_csv(section_title, file_string)
            # TODO: include validation
            # add data section title to nest 'bare' data under data section
            # => artificially increase and decrease level (see below)
            is_bare_data = (is_data_section and self.is_bare_section(section_title))
            if is_bare_data: self.increase_level(mp_level01_titles[1])
            # mark data section with special 'data ' prefix
            if is_data_section and not \
               self.section_titles[-1].startswith(mp_level01_titles[1]):
                self.section_titles[-1] = ' '.join([
                    mp_level01_titles[1], self.section_titles[-1]
                ])
            # also prepend 'data ' to the table name(s) in `plots`
            if self.level == 2 and self.section_titles[1] == mp_level01_titles[2]:
                pd_obj['table'] = ' '.join([mp_level01_titles[1], pd_obj['table']])
            # make default plot for each table, first column as x-column
            if is_data_section:
                self.document.rec_update(nest_dict(
                    {'x': pd_obj.columns[0], 'table': self.section_titles[-1]},
                    [self.section_titles[0], mp_level01_titles[2],
                     'default {}'.format(self.section_titles[-1])]
                ))
            # update nested dict/document based on section level
            self.document.rec_update(nest_dict(
                pandas_to_dict(pd_obj), self.section_titles
            ))
            if is_bare_data: self.reduce_level()
