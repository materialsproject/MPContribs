# -*- coding: utf-8 -*-
import os
from mpcontribs.users.utils import duplicate_check

@duplicate_check
def run(mpfile, **kwargs):
    identifier = mpfile.ids[0]
    contcar = os.path.join(os.path.dirname(__file__), 'CONTCAR')
    input_string = open(contcar, 'r').read()
    mpfile.add_structure(input_string, name='BiSe', identifier=identifier, fmt='poscar')
