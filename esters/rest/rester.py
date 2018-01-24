# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from mpcontribs.rest.rester import MPContribsRester

class EstersRester(MPContribsRester):
    query = {'author': 'Marco Esters'}
    #provenance_keys = ['author', 'description']
    released = True
