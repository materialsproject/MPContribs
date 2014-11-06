import re, logging
import numpy as np
import pandas as pd
from StringIO import StringIO
import config

class RecursiveDict(dict):
    """https://gist.github.com/Xjs/114831"""
    def rec_update(self, other):
        for key,value in other.iteritems():
            if key in self and \
               isinstance(self[key], dict) and \
               isinstance(value, dict):
                self[key] = RecursiveDict(self[key])
                self[key].rec_update(value)
            else:
                self[key] = value

class RecursiveParser:
    def __init__(self):
        self.level = config.min_indent_level # level counter
        self.section_titles = None
        self.document = None
        self.main_general = False
        self.level0_counter = None

    def init(self, fileExt='csv'):
        """init and set read_csv options"""
        # TODO better organize read_csv options -> config file?
        if fileExt != 'csv' and fileExt != 'tsv':
            raise ValueError('%s format not supported!' % fileExt)
        self.level0_counter = 0
        self.section_titles = []
        self.document = RecursiveDict({})
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
        return r'(?:^|\n+)%s{%d}\s+(.+)\n+' % (config.indent_symbol, self.level)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case"""
        return re.split(
            r'%s*' % config.csv_comment_char, title
        )[0].strip().lower()

    def read_csv(self, title, body):
        """run pandas.read_csv on (sub)section body"""
        options = self.data_options if title == config.mp_level01_titles[1] or (
          title != config.mp_level01_titles[0] and 
          self.level-1 == config.min_indent_level
        ) else self.colon_key_value_list
        return pd.read_csv(
            StringIO(body), comment=config.csv_comment_char,
            skipinitialspace=True, squeeze=True, **options
        ).dropna()

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

    def parse(self, file_string):
        """recursively parse sections according to number of separators"""
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            sections = sections[1:] # https://docs.python.org/2/library/re.html#re.split
            for section_index,section_body in enumerate(sections[1::2]):
                clean_title = self.clean_title(sections[2*section_index])
                if self.level == config.min_indent_level: # level-0
                    if section_index == 0: # check for main-general mode
                        self.main_general = (
                            clean_title == config.mp_level01_titles[0]
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
            pd_obj = self.read_csv(self.section_titles[-1], file_string)
            logging.info(pd_obj)
            # TODO: include validation
            # update nested dict/document based on section level
            nested_dict = self.to_dict(pd_obj)
            for key in reversed(self.section_titles):
                nested_dict = {key: nested_dict}
            self.document.rec_update(nested_dict)
