#!/usr/bin/env python
import numpy as np
import pandas as pd
from StringIO import StringIO
import json, sys, re, string, logging
import matplotlib.pyplot as plt
import collections
pd.options.display.mpl_style = 'default'

def xmcd_post_process(pdobj):
    # TODO: needs to be discussed and generalized
    # TODO: maybe implement for general case via df.apply()?
    #  http://pandas.pydata.org/pandas-docs/stable/basics.html#function-application
    # following check is enough if only 'data' section of type 'DataFrame'
    if isinstance(pdobj, pd.Series): return pdobj
    pdobj['Counter 1'] -= pdobj['Counter 0']
    pdobj = pdobj.filter(items=['Energy', 'Mag Field', 'Counter 1'])
    neg_field = pdobj[pdobj['Mag Field'] < 0.].copy()
    neg_field['Counter 1'] /= neg_field[neg_field.Energy < 773.]['Counter 1'].sum()
    pos_field = pdobj[pdobj['Mag Field'] > 0.].copy()
    pos_field['Counter 1'] /= pos_field[pos_field.Energy < 773.]['Counter 1'].sum()
    pos_field.set_index(neg_field.index, inplace=True)
    xas = (neg_field['Counter 1'] + pos_field['Counter 1']) / 2.
    xmcd = neg_field['Counter 1'] - pos_field['Counter 1']
    xmcd_df = pd.DataFrame(data={
        'Energy': neg_field['Energy'],
        'Intensity B<0': neg_field['Counter 1'],
        'Intensity B>0': pos_field['Counter 1'],
        'XMCD': xmcd, 'XAS': xas
    })
    xmcd_df.to_csv(path_or_buf=open('xmcd_post_process.csv','w'), index=False)
    return xmcd_df


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
    def __init__(self, fileExt='csv', post_process=False):
        self.post_process = post_process
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
            # example to post-process raw xmcd data before committing to DB
            if self.post_process and self.section_titles[0] == 'xmcd':
                pd_obj = xmcd_post_process(pd_obj)
            logging.info(pd_obj)
            # update nested dict/document based on section level
            nested_dict = self.to_dict(pd_obj)
            for key in reversed(self.section_titles):
                nested_dict = {key: nested_dict}
            self.document.rec_update(nested_dict)

def plot(filename):
    """plot all data based on output.json (-> plot.ly in future?)"""
    doc = json.load(open(filename,'r'))
    for key,value in doc.iteritems():
        if key == 'general': continue
        value_is_dict = isinstance(value, dict)
        data = value.get('data') if value_is_dict else value
        fig, ax = plt.subplots(1, 1)
        plotopts = value.get('plot', {}) if value_is_dict else {}
        #if plotopts.get('table'): ax.get_xaxis().set_visible(False)
        if data is not None:
            pd.DataFrame.from_dict(data).plot(ax=ax, **plotopts)
            plt.savefig('png/%s' % key.replace(' ','_'), dpi=300, bbox_inches='tight')

def submit_snl_from_cif(submitter_email, cif_file, metadata_file):
        """
        method to submit StructureNL object generated from CIF file via separate
        file containing MetaData in YAML format as required by the MPStructureNL
        constructor. Developed to be used for the submission of new structures
        during RSC publishing process (pilot project).

        Args:
            metadata_file: name of file parsed via monty's loadfn
        """
        from monty.serialization import loadfn
        from pymatgen.core import Structure
        from pymatgen.matproj.snl import StructureNL
        from mpworks.submission.submission_mongo import SubmissionMongoAdapter
        sma = SubmissionMongoAdapter.auto_load()
        pth = os.path.dirname(os.path.realpath(__file__))
        structure = Structure.from_file(os.path.join(pth, cif_file))
        config = loadfn(os.path.join(pth, metadata_file))
        if not config['references'].startswith('@'):
            config['references'] = open(
                os.path.join(pth, config['references']),'r'
            ).read()
        snl = StructureNL(structure, **config)
        sma.submit_snl(snl, submitter_email)

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", help="mp-formatted csv/tsv file")
    parser.add_argument("--outfile", help="json output file", default='test_files/output.json')
    parser.add_argument("--log", help="show log output", action="store_true")
    args = parser.parse_args()
    loglevel = 'DEBUG' if args.log else 'WARNING'
    logging.basicConfig(
        format='%(message)s', level=getattr(logging, loglevel)
    )
    if args.infile is None:
        submit_snl_from_cif(
            'Patrick Huck <phuck@lbl.gov>', 'test_filesFe3O4.cif',
            'test_files/input_rsc.yaml'
        )
    else:
        filestr = open(args.infile,'r').read()
        # init RecursiveParser with file extension to identify data column separator
        # and flag for post processing
        csv_parser = RecursiveParser(
            fileExt=os.path.splitext(args.infile)[1][1:],
            post_process=(args.infile=='test_files/input_xmcd.tsv')
        )
        csv_parser.recursive_parse(filestr)
        json.dump(
            csv_parser.document, open(args.outfile, 'wb'),
            indent=2, sort_keys=True
        )
        plot(args.outfile)
