import re, logging
import numpy as np
import pandas as pd
from StringIO import StringIO

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
    def __init__(self, fileExt='csv'):
        self.symbol = '>'
        self.min_level = 3 # minimum level to avoid collision w/ '>>'
        self.level = self.min_level # level counter
        self.section_titles = []
        self.document = RecursiveDict({})
        # TODO better organize read_csv options -> config file?
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
        return r'(?:^|\n+)%s{%d}\s+(.+)\n+' % (self.symbol, self.level)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case"""
        return re.split(r'#*', title)[0].strip().lower()

    def read_csv(self, title, body):
        """run pandas.read_csv on (sub)section body"""
        options = self.data_options if title == 'data' or (
            title != 'general' and self.level-1 == self.min_level
        ) else self.colon_key_value_list
        return pd.read_csv(
            StringIO(body), comment='#', skipinitialspace=True, squeeze=True, **options
        )

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
            outtype = 'list' if all_columns_numeric else 'records'
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

    def recursive_parse(self, file_string):
        """recursively parse sections according to number of separators"""
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            sections = sections[1:] # https://docs.python.org/2/library/re.html#re.split
            for section_index,section_body in enumerate(sections[1::2]):
                clean_title = self.clean_title(sections[2*section_index])
                self.increase_level(clean_title)
                self.recursive_parse(section_body)
                self.reduce_level()
        else:
            # separator level not found b/c too high
            # read csv / convert section body to pandas object
            pd_obj = self.read_csv(self.section_titles[-1], file_string)
            # TODO: include validation
            logging.info(pd_obj)
            # update nested dict/document based on section level
            nested_dict = self.to_dict(pd_obj)
            for key in reversed(self.section_titles):
                nested_dict = {key: nested_dict}
            self.document.rec_update(nested_dict)
