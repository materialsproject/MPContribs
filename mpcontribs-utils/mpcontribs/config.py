import os, re
from tempfile import gettempdir

mp_level01_titles = [ '_hdata', 'tables', 'graphs', 'structures' ]
csv_comment_char = '#'
mp_id_pattern = re.compile('^(mp|por|mvc)-\d+(?:--\d+)?$', re.IGNORECASE)
object_id_pattern = re.compile('^[a-f\d]{24}$')
default_mpfile_path = os.path.join(gettempdir(), 'mpfile.txt')
symprec = 1e-10
replacements = {' ': '_', '[': '', ']': '', '{': '', '}': '', ':': '_'}
