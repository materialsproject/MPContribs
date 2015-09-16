from __future__ import unicode_literals, print_function
import os, re, pwd, six
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict
from mpcontribs.config import SITE
from mpcontribs.rest.rester import MPContribsRester
from importlib import import_module

ENDPOINT, API_KEY = "{}/rest".format(SITE), os.environ.get('MAPI_KEY_LOC')

def get_short_object_id(cid):
    length = 7
    cid_short = str(cid)[-length:]
    if cid_short == '0'*length:
        cid_short = str(cid)[:length]
    return cid_short

def submit_mpfile(path_or_mpfile, fmt='archieml'):
    with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
        yield 'DB connection ... '
        ncontribs = mpr.get_number_of_contributions()
        if ncontribs is None:
            yield  'FAILED.</br>'
            return
        yield 'OK ({} contributions).</br>'.format(ncontribs)
    # check whether user in group of contributors, then
    # submit to MP by <user> (<project/institute>) via
    # calling process_mpfile with target=mpr (abort option?)

def process_mpfile(path_or_mpfile, target=None, fmt='archieml'):
    if isinstance(path_or_mpfile, six.string_types) and \
       not os.path.isfile(path_or_mpfile):
        yield '{} not found'.format(path_or_mpfile)
        return
    mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
    MPFile = getattr(mod, 'MPFile')
    if target is None:
        from mpcontribs.rest.adapter import ContributionMongoAdapter
        from mpcontribs.builders import MPContributionsBuilder
        full_name = pwd.getpwuid(os.getuid())[4]
        contributor = '{} <phuck@lbl.gov>'.format(full_name)
        cma = ContributionMongoAdapter()
    # split input MPFile into contributions: treat every mp_cat_id as separate DB insert
    mpfile, cid_shorts = MPFile.from_dict(), [] # output
    for idx, mpfile_single in enumerate(MPFile.from_file(path_or_mpfile).split()):
        mp_cat_id = mpfile_single.document.keys()[0]
        cid = mpfile_single.document[mp_cat_id].get('cid', None)
        update = bool(cid is not None)
        if update:
            cid_short = get_short_object_id(cid)
            yield 'use contribution #{} to update ID #{} ... '.format(idx, cid_short)
        else:
            yield 'submit contribution #{} ... '.format(idx, mp_cat_id)
        if target is not None:
            cid = target.submit_contribution(mpfile_single)
        else:
            doc = cma.submit_contribution(mpfile_single, contributor)
            cid = doc['_id']
        cid_short = get_short_object_id(cid)
        yield 'done.</br>' if update else 'done (ID #{}).</br>'.format(cid_short)
        mpfile_single.insert_id(mp_cat_id, cid)
        cid_shorts.append(cid_short)
        yield 'build contribution #{} into {} ... '.format(idx, mp_cat_id)
        if target is not None:
            url = target.build_contribution(cid)
            yield 'done, see {}/{}.</br>'.format(SITE, url)
        else:
            mcb = MPContributionsBuilder(doc)
            yield mcb.build(contributor, cid)
            yield 'done.</br>'.format(idx, cid_short)
        mpfile.concat(mpfile_single)
    ncontribs = len(cid_shorts)
    if target is not None and \
       isinstance(path_or_mpfile, six.string_types) and \
       os.path.isfile(path_or_mpfile):
        yield 'embed #{} in MPFile ...'.format('/'.join(cid_shorts))
        mpfile.write_file(path_or_mpfile, with_comments=True)
        yield '<strong>{} contributions successfully submitted.</strong>'.format(ncontribs)
    else:
        yield '<strong>{} contributions successfully processed.</strong>'.format(ncontribs)

def flatten_dict(dd, separator='.', prefix=''):
    """http://stackoverflow.com/a/19647596"""
    return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_dict(vv, separator, kk).items()
           } if isinstance(dd, dict) else { prefix : dd }

def unflatten_dict(d):
    for k in d:
        value, keys = d.pop(k), k.split('.')
        d.rec_update(nest_dict({keys[-1]: value}, keys[:-1]))
