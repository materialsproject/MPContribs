import re, logging
import numpy as np
import pandas as pd
from StringIO import StringIO
from ..config import min_indent_level, indent_symbol, csv_comment_char, mp_level01_titles
from base import BaseParser

class RecursiveParser(BaseParser):
    def __init__(self, fileExt='csv'):
        """init and set read_csv options"""
        BaseParser.__init__(self)
        self.level = min_indent_level # level counter
        # TODO better organize read_csv options -> config file?
        if fileExt != 'csv' and fileExt != 'tsv':
            raise ValueError('%s format not supported!' % fileExt)
        data_separator = '\t' if fileExt == 'tsv' else ','
        self.data_options = { 'sep': data_separator, 'header': 0 }
        self.colon_key_value_list = { 'sep': ':', 'header': None, 'index_col': 0 }

    def separator_regex(self):
        """get separator regex for section depth/level"""
        # (?:  ) => non-capturing group
        # (?:^|\n+) => match beginning of string OR one or more newlines
        # >{3}\s+ => match '>' repeated 3 times followed by on or more spaces
        #    require minimum one space after section level identifier
        # (.+) => capturing group of one or more arbitrary characters
        # \n+ => end by one or more newlines
        return r'(?:^|\n+)%s{%d}\s+(.+)\n+' % (indent_symbol, self.level)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case"""
        return re.split(
            r'%s*' % csv_comment_char, title
        )[0].strip().lower()

    def is_bare_data_section(self, title):
        """determine whether currently in bare data section"""
        return (
            title != mp_level01_titles[0] and 
            self.level-1 == min_indent_level
        )

    def is_data_section(self, title):
        """determine whether currently in data section"""
        return (
            title == mp_level01_titles[1] or
            self.is_bare_data_section(title)
        )

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
        if self.is_data_section(title):
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
        return pd.read_csv(
            StringIO(body), comment=csv_comment_char,
            skipinitialspace=True, squeeze=True,
            converters = converters,
            **options
        ).dropna(how='all')

    def to_dict(self, pandas_object):
        """convert pandas object to dict"""
        if isinstance(pandas_object, pd.Series):
            return pandas_object.to_dict()
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

    def nest_dict(self, dct, keys):
        """nest dict under list of keys"""
        nested_dict = dct
        for key in reversed(keys):
            nested_dict = {key: nested_dict}
        return nested_dict

    def parse(self, file_string):
        """recursively parse sections according to number of separators"""
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            sections = sections[1:] # https://docs.python.org/2/library/re.html#re.split
            for section_index,section_body in enumerate(sections[1::2]):
                clean_title = self.clean_title(sections[2*section_index])
                if self.level == min_indent_level: # level-0
                    if section_index == 0: # check for main-general mode
                        self.main_general = (
                            clean_title == mp_level01_titles[0]
                        )
                    elif self.main_general: # uniquify level-0 titles
                        clean_title += '--%d' % self.level0_counter
                        self.level0_counter += 1
                self.increase_level(clean_title)
                self.parse(section_body)
                self.reduce_level()
        else:
            # separator level not found b/c too high
            # read csv / convert section body to pandas object
            section_title = self.section_titles[-1]
            pd_obj = self.read_csv(section_title, file_string)
            logging.info(pd_obj)
            # TODO: include validation
            # add first column as x-column for default plot
            if self.is_data_section(section_title):
                nested_keys = [
                    self.section_titles[0],
                    mp_level01_titles[2], 'default'
                ]
                self.document.rec_update(self.nest_dict(
                    {'x': pd_obj.columns[0]}, nested_keys
                ))
            # add data section title to nest 'bare' data under data section
            # => artificially increase and decrease level (see below)
            is_bare_data = False
            if self.is_bare_data_section(section_title):
                is_bare_data = True
                self.increase_level(mp_level01_titles[1])
            # update nested dict/document based on section level
            self.document.rec_update(self.nest_dict(
                self.to_dict(pd_obj), self.section_titles
            ))
            if is_bare_data: self.reduce_level()
