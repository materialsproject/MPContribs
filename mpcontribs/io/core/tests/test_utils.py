# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from nose.tools import *
from mpcontribs.io.core.utils import *

def test_get_short_object_id():
    cid = '5a8638add4f144413451852a'
    short_cid = get_short_object_id(cid)
    assert_equal(short_cid, '451852a')

def test_make_pair():
    assert_equal(make_pair('Phase', 'Hollandite'), 'Phase: Hollandite')
    assert_equal(make_pair('ΔH', '0.066 eV/mol'), 'ΔH: 0.066 eV/mol')

