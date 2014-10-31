#from mp_input_file_v0 import MPInputFile
from mp_input_file_v1 import MPInputFile

f = MPInputFile()
#f.make_file()
for i in range(5):
    print f._get_level_n_section_line(0, i)
