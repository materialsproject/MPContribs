#!/usr/bin/env python
import pandas as pd
from StringIO import StringIO
import json, sys, re, string, logging
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'

class RecursiveParser:
    def __init__(self):
        self.symbol = '>'
        self.min_level = 3 # minimum level to avoid collision w/ '>>'
        self.max_level = 6 # maximum section-nesting supported
        self.level = self.max_level # level counter
        self.max_level_found = False
        self.section_title = None
        # TODO better organize read_csv options
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

    def read_csv(self, body):
        """run pandas.read_csv on (sub)section body"""
        return pd.read_csv(
            StringIO(body), comment='#', skipinitialspace=True, squeeze=True,
            **self.special_options.get(self.section_title, self.default_options)
        )

    def recursive_parse(self, file_string):
        """recursively parse sections according to number of separators"""
        # return if below minimum section level
        if self.level < self.min_level:
            pd_obj = self.read_csv(file_string)
            self.level = self.max_level
            logging.info(
                'below level %d\n%r\n-> reset level to %d',
                self.min_level, pd_obj, self.max_level
            )
            return
        # split into section title line (even) and section body (odd entries)
        sections = re.split(self.separator_regex(), file_string)
        if len(sections) > 1:
            # separator found. leading empty string, see
            # https://docs.python.org/2/library/re.html#re.split
            if not self.max_level_found: # TODO smarter?
                self.max_level_found = True
                self.max_level = self.level
                logging.info('reset max_level to %d', self.max_level)
            sections = sections[1:]
            for section_index,section_body in enumerate(sections[1::2]):
                self.section_title = self.clean_title(sections[2*section_index])
                logging.info('level: %d, %s', self.level, self.section_title)
                self.level -= 1
                self.recursive_parse(section_body)
        else:
            # separator not found -> section level too high
            # file_string = sections[0]
            logging.info('no sep at level %d', self.level)
            self.level -= 1
            self.recursive_parse(file_string)

#def to_dict(pandas_object):
#    """convert pandas object to python dictionary w/ correct outtype options"""
#    if isinstance(pandas_object, pd.Series):
#        return pandas_object.to_dict()
#    # DataFrame outtype = 'dict'(default), 'list', 'series', 'records'
#    return pandas_object.to_dict() #TODO
#
#def import_csv(filename):
#    """import MP-formatted csv file into MP database"""
#
#    # iterate sections
#    sections = re.split(section_separator_regex, filestr)
#    sections = sections[1:]
#    doc = {}
#    for section_index,section_body in enumerate(sections[1::2]):
#        section_title = clean_title(sections[2*section_index])
#        subsections = re.split(subsection_separator_regex, section_body)
#
#        # 'general'-section or section with no subsections (i.e. only data)
#        if len(subsections) == 1:
#            pd_obj = read_csv(section_title, subsections[0]) # pandas object
#            print pd_obj
#            doc[section_title] = to_dict(pd_obj)
#            print section_title, type(pd_obj), doc[section_title]
#            continue
# 
#        # section with subsections 'general' or 'plot' or 'data'
#        subsections = subsections[1:] # dirty fix to omit leading empty string
#        doc[section_title] = {}
#        for subsection_index,subsection_body in enumerate(subsections[1::2]):
#            subsection_title = clean_title(subsections[2*subsection_index])
#            pd_obj = read_csv(subsection_title, subsection_body)
#            doc[section_title][subsection_title] = to_dict(pd_obj)
#
#    #json.dump(doc, open('output.json','wb'), indent=2, sort_keys=True)
#
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
    #import_csv(filestr)
    #plot('output.json')
