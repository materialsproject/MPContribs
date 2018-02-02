# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from mpcontribs.rest.rester import MPContribsRester

class AlsBeamlineRester(MPContribsRester):
    """ALS Beamline-specific convenience functions to interact with MPContribs REST interface"""
    query = {'content.measurement_location': 'ALS Beamline 6.3.1'}
    provenance_keys = [
        'title', 'authors', 'measurement_location', 'sample'
    ] #'description', 'dois'
