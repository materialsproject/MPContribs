from nose.tools import *
from mpcontribs.io.archieml.mpfile import MPFile

def test_get_string():
    mpfile = MPFile.from_file('test_files/test_archieml.txt')
    mpfile_test = MPFile.from_string(mpfile.get_string())
    assert_equal(mpfile.document, mpfile_test.document)
