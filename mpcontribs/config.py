from __future__ import unicode_literals, print_function
import os, re

indent_symbol = '>'
min_separator_length = 3 # minimum separator length to avoid collision w/ '>>'
mp_categories = {
    'mp_id': [
        'numerify', 'mp-####'
    ], # mp-id, e.g. mp-1234
    'composition': [
        'numerify', 'A#B#'
    ], # composition, e.g. A2B3
    'chemical_system': [
        'lexify', '??'
    ], # chem. system, e.g. AB
}
mp_level01_titles = [ 'general', 'data', 'plots' ]
csv_comment_char = '#'
csv_database = os.path.join(
  os.path.dirname(os.path.realpath(__file__)),
  '../test_files/lahman-csv_2014-02-14'
)
#SITE = 'https://www.materialsproject.org'
SITE = 'http://127.0.0.1:8000'
mp_id_pattern = re.compile('^(mp|por)-\d+$', re.IGNORECASE)
default_mpfile_path = '/tmp/mpfile.txt'
