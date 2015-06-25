import re, logging
import numpy as np
import pandas as pd
from StringIO import StringIO
from ..config import min_indent_level, indent_symbol, csv_comment_char, mp_level01_titles
from utils import nest_dict, RecursiveDict
from collections import OrderedDict

class RecursiveParser():
    def __init__(self, fileExt):
        """init and set read_csv options"""
        self.level0_counter = 0
        self.section_titles = []
        self.document = RecursiveDict({})
        self.level = min_indent_level # level counter
        self.data_options = { 'sep': ',', 'header': 0 }
        self.colon_key_value_list = { 'sep': ':', 'header': None, 'index_col': 0 }
        self.mp_id_pattern = re.compile('mp-\d+', re.IGNORECASE)

    def separator_regex(self):
        """get separator regex for section depth/level"""
        # (?:  ) => non-capturing group
        # (?:^|\n+) => match beginning of string OR one or more newlines
        # %s{%d}\s+ => match indent_symbol*level followed by one or more spaces
        #    require minimum one space after section level identifier
        # (.+) => capturing group of one or more arbitrary characters
        # (?:$|\n*?) => match end-of-string OR zero or more newlines
        #    be non-greedy with newlines at end of string
        return r'(?:^|\n+)%s{%d}\s+(.+)(?:$|\n*?)' % (indent_symbol, self.level)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case if mp-id"""
        title = re.split(
            r'%s*' % csv_comment_char, title
        )[0].strip()
        is_mp_id = (
          self.level == min_indent_level and
          self.mp_id_pattern.match(title)
        )
        return title.lower() if is_mp_id else title

    def is_bare_section(self, title):
        """determine whether currently in bare section"""
        return (
            title != mp_level01_titles[0] and 
            self.level-1 == min_indent_level
        )

    def is_data_section(self, body):
        """determine whether currently in data section"""
        return (indent_symbol*min_indent_level not in body and ':' not in body)

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
            converters = converters,
            **options
        ).dropna(how='all')

    def to_dict(self, pandas_object):
        """convert pandas object to dict"""
        if pandas_object is None: return {}
        if isinstance(pandas_object, pd.Series):
            return OrderedDict((k,v) for k,v in pandas_object.iteritems())
        all_columns_numeric = True
        for col in pandas_object.columns:
            if ( pandas_object[col].dtype != np.float64 and \
                pandas_object[col].dtype != np.int64 ):
                all_columns_numeric = False
                break
        return pandas_object.to_dict(
            orient = 'list' if all_columns_numeric else 'records'
        )

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
                if self.level == min_indent_level and clean_title in self.document:
                    clean_title += '--%d' % self.level0_counter
                    self.level0_counter += 1
                self.increase_level(clean_title)
                self.parse(section_body)
                self.reduce_level()
        else:
            # separator level not found, convert section body to pandas object,
            section_title = self.section_titles[-1]
            is_data_section, pd_obj = self.read_csv(section_title, file_string)
            logging.info(pd_obj)
            # TODO: include validation
            # add data section title to nest 'bare' data under data section
            # => artificially increase and decrease level (see below)
            is_bare_data = (is_data_section and self.is_bare_section(section_title))
            if is_bare_data: self.increase_level(mp_level01_titles[1])
            # use first csv table for default plot, first column as x-column
            if is_data_section and (
                self.section_titles[0] not in self.document or
                mp_level01_titles[2] not in self.document[self.section_titles[0]]
            ):
                self.document.rec_update(nest_dict(
                    {'x': pd_obj.columns[0], 'table': self.section_titles[-1]},
                    [self.section_titles[0], mp_level01_titles[2], 'default']
                ))
            # update nested dict/document based on section level
            self.document.rec_update(nest_dict(
                self.to_dict(pd_obj), self.section_titles
            ))
            if is_bare_data: self.reduce_level()
