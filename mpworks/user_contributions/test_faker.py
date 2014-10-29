from mpworks.user_contributions.fakers import CsvInputFile
f = CsvInputFile()
for i in range(5):
    print f._get_level_n_section_line(i)
