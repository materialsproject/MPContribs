import os
from mpcontribs.io.archieml.mpfile import MPFile

def test_get_string():
    test_file = os.path.join(os.path.dirname(__file__), 'test_archieml.txt')
    mpfile = MPFile.from_file(test_file)
    mpfile_test = MPFile.from_string(mpfile.get_string())
    assert mpfile.document == mpfile_test.document
