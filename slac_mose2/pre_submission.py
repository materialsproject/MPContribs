# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import tarfile, os, sys
from mpcontribs.io.archieml.mpfile import MPFile
from mpcontribs.config import mp_level01_titles
from mpcontribs.users.utils import duplicate_check
from mpcontribs.io.core.utils import read_csv
from itertools import permutations

@duplicate_check
def run(mpfile, **kwargs):
    from pandas import Panel, np

    meta_data = mpfile.document['_hdata'].pop('input')
    file_path = os.path.join(os.environ['HOME'], 'work', meta_data['file_path'])
    if not os.path.exists(file_path):
        print 'Please upload', file_path
        return

    table_columns = meta_data['table_columns'].split(' -- ')
    identifier = mpfile.ids[0]

    with tarfile.open(file_path, "r:gz") as tar:
        for member in tar.getmembers():
            name = os.path.splitext(member.name)[0]
            print 'load', name, '...'
            f = tar.extractfile(member)
            if 'pump' in name:
                #fstr = f.read()
                #fstr = ''.join([f.readline() for x in xrange(10)])
                # only load a small area
                list1, list2 = range(1), range(6)
                tuples = [(x, y) for x in list1 for y in list2]
                delta = 150
                for x, y in tuples:
                    lines = []
                    for i in xrange((x+1)*delta):
                        line = f.readline()
                        if i > x*delta:
                            lines.append(line)
                    sub_lines = []
                    for line in lines:
                        sub_line = line.strip().split(',')[y*delta:(y+1)*delta]
                        sub_lines.append(','.join(sub_line))
                    fstr = '\n'.join(sub_lines)
                    print 'read_csv ...'
                    df = read_csv(fstr, header=None)
                    arr = [[[cell] for cell in row] for row in df.values]
                    sub_name = '{}_{}_{}'.format(name, x, y)
                    df = Panel(arr, minor_axis=[sub_name]).transpose(2, 0, 1).to_frame()
                    print df.head()
                    print 'add', sub_name, '...'
                    mpfile.add_data_table(identifier, df, sub_name)
                    f.seek(0)
            else:
                fstr = f.read()
                df = read_csv(fstr, names=table_columns)
                print 'add', name, '...'
                mpfile.add_data_table(identifier, df, name)

    print 'Added data from {}'.format(file_path)
