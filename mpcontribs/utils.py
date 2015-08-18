from __future__ import unicode_literals, print_function
import os, re, pwd
from six import string_types
from io.utils import nest_dict, RecursiveDict
from mpcontribs.config import SITE

def get_short_object_id(cid):
    length = 7
    cid_short = str(cid)[-length:]
    if cid_short == '0'*length:
        cid_short = str(cid)[:length]
    return cid_short

def submit_mpfile(path_or_mpfile, target=None, test=False):
    if isinstance(path_or_mpfile, string_types) and \
       not os.path.isfile(path_or_mpfile):
        print('{} not found'.format(path_or_mpfile))
        return
    from mpcontribs.io.custom.mpfile import MPFile
    if target is None:
        from mpcontribs.rest import ContributionMongoAdapter
        from mpcontribs.builders import MPContributionsBuilder
        full_name = pwd.getpwuid(os.getuid())[4]
        contributor = '{} <phuck@lbl.gov>'.format(full_name)
        cma = ContributionMongoAdapter()
        build_doc = RecursiveDict()
    # split input MPFile into contributions: treat every mp_cat_id as separate DB insert
    mpfile, cid_shorts = MPFile(), [] # output
    for idx, mpfile_single in enumerate(MPFile.from_file(path_or_mpfile).split()):
        mp_cat_id = mpfile_single.document.keys()[0]
        cid = mpfile_single.document[mp_cat_id].get('cid', None)
        if test and cid is None: mpfile_single.set_test_mode(mp_cat_id, idx)
        if cid is None:
            print('submit contribution for {} ...'.format(mp_cat_id))
        else:
            cid_short = get_short_object_id(cid)
            print('update contribution #{} for {} ...'.format(cid_short, mp_cat_id))
        if target is not None:
            mpfile_single.write_file('tmp')
            cid = target.submit_contribution('tmp')
            os.remove('tmp')
        else:
            doc = cma.submit_contribution(mpfile_single, contributor)
            cid = doc['_id']
        cid_short = get_short_object_id(cid)
        print('> submitted as #{}'.format(cid_short))
        mpfile_single.insert_id(mp_cat_id, cid)
        cid_shorts.append(cid_short)
        print('> build contribution #{} into {} ...'.format(cid_short, mp_cat_id))
        if target is not None:
            url = target.build_contribution(cid)
            print('> built #{}, see {}/{}'.format(cid_short, SITE, url))
        else:
            mcb = MPContributionsBuilder(doc)
            single_build_doc = mcb.build(contributor, cid)
            build_doc.rec_update(single_build_doc)
            print('> built #{}'.format(cid_short))
        mpfile.concat(mpfile_single)
    if target is not None and \
       isinstance(path_or_mpfile, string_types) and \
       os.path.isfile(path_or_mpfile):
        print('> embed #{} in MPFile ...'.format('/'.join(cid_shorts)))
        mpfile.write_file(path_or_mpfile, with_comments=True)
    else:
        return build_doc

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
