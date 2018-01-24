# -*- coding: utf-8 -*-
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):
    identifier = mpfile.ids[0]
    input_string = open('CONTCAR', 'r').read()
    mpfile.add_structure(input_string, name='BiSe', identifier=identifier, fmt='poscar')
    print mpfile
