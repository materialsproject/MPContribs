import os

indent_symbol = '>'
min_indent_level = 3 # minimum level to avoid collision w/ '>>'
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
  'test_files/lahman-csv_2014-02-14'
)
