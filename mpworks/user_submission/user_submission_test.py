#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json, sys, re, string, logging
import matplotlib.pyplot as plt
import collections
pd.options.display.mpl_style = 'default'

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
        self.symbol = '>'
        self.min_level = 3 # minimum level to avoid collision w/ '>>'
        self.max_level = 6 # maximum section-nesting supported
        self.level = self.max_level # level counter
        self.section_titles = [None] * (self.max_level-self.min_level+1)
        self.document = RecursiveDict({})
        # TODO better organize read_csv options -> config file?
        self.default_options = { 'sep': ',', 'header': 0 } # csv data
        self.colon_key_value_list = { 'sep': ':', 'header': None, 'index_col': 0 }
        self.special_options = {
            'general': self.colon_key_value_list,
            'plot': self.colon_key_value_list
        }

    def separator_regex(self):
        """get separator regex for section depth/level"""
        return r'\n*%s{%d}(.+)\n*' % (self.symbol, self.level)

    def clean_title(self, title):
        """strip in-line comments & spaces, make lower-case"""
        return re.split(r'#*', title)[0].strip().lower()

    def read_csv(self, title, body):
        """run pandas.read_csv on (sub)section body"""
        return pd.read_csv(
            StringIO(body), comment='#', skipinitialspace=True, squeeze=True,
            **self.special_options.get(title, self.default_options)
        )

    def recursive_parse(self, file_string):
        """recursively parse sections according to number of separators"""
        logging.info('-> new level: %d', self.level)
        # return if below minimum section level
        if self.level < self.min_level:
            section_titles = filter(None, self.section_titles)
            pd_obj = self.read_csv(section_titles[-1], file_string)
            logging.info(pd_obj)
            nested_dict = pd_obj.to_dict() \
                    if isinstance(pd_obj, pd.Series) \
                    else pd_obj.to_dict('records')
            for key in reversed(section_titles):
                nested_dict = {key: nested_dict}
            self.document.rec_update(nested_dict)
            logging.info('=========')
            return
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            logging.info('separator %s found', self.symbol*self.level)
            sections = sections[1:] # https://docs.python.org/2/library/re.html#re.split
            for section_index,section_body in enumerate(sections[1::2]):
                clean_title = self.clean_title(sections[2*section_index])
                level_index = self.max_level - self.level
                self.section_titles[level_index] = clean_title
                logging.info(self.section_titles)
                self.level -= 1
                self.recursive_parse(section_body)
                self.level += 1
                self.section_titles[level_index] = None
        else:
            # separator not found -> file_string = sections[0]
            self.level -= 1
            self.recursive_parse(file_string)
            self.level += 1

#def plot(filename):
#    """plot all data based on output.json (-> plot.ly in future?)"""
#    doc = json.load(open(filename,'r'))
#    for section_name,section_body in doc.iteritems():
#        if section_name != 'general':
#            print section_name, section_body.keys()
#    #fig, ax = plt.subplots(1, 1)
#    #if Table: ax.get_xaxis().set_visible(False)
#    #df.plot(ax=ax, **plotopts[i])
#    #plt.savefig('png/fig%d' % i, dpi=300, bbox_inches='tight')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", help="mp-formatted csv file")
    parser.add_argument("--log", help="show log output", action="store_true")
    args = parser.parse_args()
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    filestr = open(args.infile,'r').read()
    csv_parser = RecursiveParser()
    csv_parser.recursive_parse(filestr)
    json.dump(
        csv_parser.document, open('output.json','wb'),
        indent=2, sort_keys=True
    )
    #plot('output.json')
