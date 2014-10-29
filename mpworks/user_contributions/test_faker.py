from mpworks.user_contributions.fakers import CsvInputFile
f = CsvInputFile()
print 'test 1 ...'
for i in range(5):
    print f._get_level_n_section_line(i)
print 'test 2 ...'
for i in range(10):
    for j in range(3):
        print f._get_level_n_section_line(j)
