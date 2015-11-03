from __future__ import unicode_literals, print_function
import os, re, pwd, six, time, json, sys
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict, get_short_object_id
from mpcontribs.config import SITE
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.rest.adapter import ContributionMongoAdapter
from mpcontribs.builders import MPContributionsBuilder
from importlib import import_module

ENDPOINT = '/'.join([SITE, 'mpcontribs', 'rest'])
API_KEY = os.environ.get('MAPI_KEY_LOC')

def submit_mpfile(path_or_mpfile, fmt='archieml'):
    with MPContribsRester(API_KEY, endpoint=ENDPOINT) as mpr:
        try:
            yield 'DB connection? ' # also checks internet connection
            ncontribs = sum(1 for contrib in mpr.query_contributions(contributor_only=True))
            yield 'OK ({} contributions).</br> '.format(ncontribs)
            time.sleep(1)
            yield 'Contributor? '
            check = mpr.check_contributor()
            yield '{} ({}).</br>'.format(check['contributor'], check['institution'])
            time.sleep(1)
            yield 'Registered? '
            if not check['is_contrib']:
                raise Exception('Please register as contributor!')
            time.sleep(1)
            yield 'YES.</br>'
            time.sleep(1)
            yield 'Cancel data transmission? '
            for i in range(5):
                yield '#'
                time.sleep(1)
            yield ' NO.</br>'
            for msg in process_mpfile(path_or_mpfile, target=mpr, fmt=fmt):
                yield msg
        except:
            ex = sys.exc_info()[1]
            yield 'FAILED.</br>'
            yield str(ex).replace('"',"'")
            return

def process_mpfile(path_or_mpfile, target=None, fmt='archieml'):
    try:
        if isinstance(path_or_mpfile, six.string_types) and \
           not os.path.isfile(path_or_mpfile):
            raise Exception('{} not found'.format(path_or_mpfile))
        mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
        MPFile = getattr(mod, 'MPFile')
        full_name = pwd.getpwuid(os.getuid())[4]
        contributor = '{} <phuck@lbl.gov>'.format(full_name) # fake
        cma = ContributionMongoAdapter()
        # split input MPFile into contributions: treat every mp_cat_id as separate DB insert
        mpfile, cid_shorts = MPFile.from_dict(), [] # output
        for idx, mpfile_single in enumerate(MPFile.from_file(path_or_mpfile).split()):
            mp_cat_id = mpfile_single.document.keys()[0]
            # TODO test update mode
            cid = mpfile_single.document[mp_cat_id].get('cid', None)
            update = bool(cid is not None)
            if update:
                cid_short = get_short_object_id(cid)
                yield 'use contribution #{} to update ID #{} ... '.format(idx, cid_short)
            # always run local "submission" to catch failure before interacting with DB
            yield 'locally process contribution #{} ... '.format(idx)
            doc = cma.submit_contribution(mpfile_single, contributor) # does not use get_string
            cid = doc['_id']
            yield 'check consistency ... '
            mpfile_single_cmp = MPFile.from_string(mpfile_single.get_string())
            if mpfile_single.document != mpfile_single_cmp.document:
                # compare json strings to find first inconsistency
                for a, b in zip(
                    json.dumps(mpfile_single.document, indent=4).split('\n'),
                    json.dumps(mpfile_single_cmp.document, indent=4).split('\n')
                ):
                    if a != b:
                        raise Exception('{} <====> {}'.format(a.strip(), b.strip()))
            if target is not None:
                yield 'submit to MP ... '
                cid = target.submit_contribution(mpfile_single, fmt) # uses get_string
            cid_short = get_short_object_id(cid)
            mpfile_single.insert_id(mp_cat_id, cid)
            cid_shorts.append(cid_short)
            yield 'build into {} ... '.format(mp_cat_id)
            if target is not None:
                url = target.build_contribution(cid)
                yield ("OK. <a href='{}/{}' class='btn btn-default btn-xs' " +
                       "role='button' target='_blank'>View</a></br>").format(SITE, url)
            else:
                mcb = MPContributionsBuilder(doc)
                yield mcb.build(contributor, cid)
                yield 'OK.</br>'.format(idx, cid_short)
            mpfile.concat(mpfile_single)
            time.sleep(.1)
        ncontribs = len(cid_shorts)
        #if target is not None and \
        #   isinstance(path_or_mpfile, six.string_types) and \
        #   os.path.isfile(path_or_mpfile):
        #    yield 'embed #{} in MPFile ...'.format('/'.join(cid_shorts))
        #    mpfile.write_file(path_or_mpfile, with_comments=True)
        if target is not None:
            yield '<strong>{} contributions successfully submitted.</strong>'.format(ncontribs)
        else:
            yield '<strong>{} contributions successfully processed.</strong>'.format(ncontribs)
    except:
        ex = sys.exc_info()[1]
        yield 'FAILED.</br>'
        yield str(ex).replace('"',"'")
        return
