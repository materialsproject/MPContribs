# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import os, re, pwd, six, time, json, sys, pkgutil
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import nest_dict, get_short_object_id
from mpcontribs.rest.rester import MPContribsRester
from mpcontribs.rest.adapter import ContributionMongoAdapter
from mpcontribs.builder import MPContributionsBuilder
from pympler import asizeof
from importlib import import_module
from StringIO import StringIO
sys.stdout.flush()

def submit_mpfile(path_or_mpfile, site='jupyterhub', fmt='archieml', project=None):
    test_site = bool('jupyterhub' in site)
    with MPContribsRester(test_site=test_site) as mpr:
        try:
            yield 'Connection to DB {} at {}? '.format(mpr.dbtype, mpr.preamble)
            ncontribs = sum(1 for contrib in mpr.query_contributions(contributor_only=True))
            yield 'OK ({} contributions).</br> '.format(ncontribs)
            time.sleep(1)
            yield 'Contributor? '
            check = mpr.check_contributor()
            yield '{} ({}).</br>'.format(check['contributor'], check['institution'])
            time.sleep(1)
            if check['group_added']:
                yield '"contrib" group added. '
            if check['contributor_added']:
                yield 'User added as contributor. '
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
            for msg in process_mpfile(path_or_mpfile, target=mpr, fmt=fmt, project=project):
                yield msg
        except:
            ex = sys.exc_info()[1]
            yield 'FAILED.</br>'
            yield unicode(ex).replace('"',"'")
            return

def json_compare(d1, d2):
    json.encoder.FLOAT_REPR = lambda o: format(o, 'g')
    def dumps(d):
        return json.dumps(d, indent=4).split('\n')

    for a, b in zip(dumps(d1), dumps(d2)):
        if a != b:
            raise Exception('{} <====> {}'.format(a.strip(), b.strip()))

def process_mpfile(path_or_mpfile, target=None, fmt='archieml', ids=None, project=None):
    try:
        if isinstance(path_or_mpfile, six.string_types) and \
           not os.path.isfile(path_or_mpfile):
            raise Exception('{} not found'.format(path_or_mpfile))

        if ids is not None and not isinstance(ids, list) and not len(ids) == 2:
            raise Exception('{} is not list of length 2!'.format(ids))

        from pymatgen.analysis.structure_matcher import StructureMatcher
        mod = import_module('mpcontribs.io.{}.mpfile'.format(fmt))
        MPFile = getattr(mod, 'MPFile')
        full_name = pwd.getpwuid(os.getuid())[4]
        contributor = '{} <phuck@lbl.gov>'.format(full_name) # fake
        cma = ContributionMongoAdapter()
        axes, ov_data = set(), dict()
        mpfile_out, cid_shorts = MPFile(), [] # output
        sm = StructureMatcher(primitive_cell=False, scale=False)

        # split input MPFile into contributions: treat every mp_cat_id as separate DB insert
        mpfile_in = path_or_mpfile
        if isinstance(path_or_mpfile, six.string_types) or isinstance(path_or_mpfile, StringIO):
            mpfile_in = MPFile.from_file(path_or_mpfile)
        for idx, mpfile_single in enumerate(mpfile_in.split()):

            mp_cat_id = mpfile_single.document.keys()[0]
            if ids is None or mp_cat_id == ids[0]:

                cid = mpfile_single.document[mp_cat_id].get('cid', None)
                update = bool(cid is not None)
                if update:
                    cid_short = get_short_object_id(cid)
                    yield 'use #{} to update #{} ... '.format(idx, cid_short)

                # always run local "submission" to catch failure before interacting with DB
                yield 'process #{} ({}) ... '.format(idx, mp_cat_id)
                # does not use get_string
                doc = cma.submit_contribution(mpfile_single, contributor, project=project)
                cid = doc['_id']
                cid_short = get_short_object_id(cid)
                if ids is None or cid_short == ids[1]:

                    yield 'check ... '
                    obj_size = asizeof.asizeof(mpfile_single) / 1024. / 1024.
                    if obj_size > 0.5:
                        yield 'skip ({:.3f}MB) ... '.format(obj_size)
                    else:
                        try:
                            mpfile_single_cmp_str = mpfile_single.get_string()
                        except Exception as ex:
                            yield 'get_string() FAILED!<br>'
                            continue
                        try:
                            mpfile_single_cmp = MPFile.from_string(mpfile_single_cmp_str)
                        except Exception as ex:
                            yield 'from_string() FAILED!<br>'
                            continue
                        if mpfile_single.document != mpfile_single_cmp.document:
                            yield 'check again ... '
                            found_inconsistency = False
                            # check hierarchical and tabular data
                            # compare json strings to find first inconsistency
                            if mpfile_single.hdata != mpfile_single_cmp.hdata:
                                yield 'hdata not OK:'
                                json_compare(mpfile_single.hdata, mpfile_single_cmp.hdata)
                            if mpfile_single.tdata != mpfile_single_cmp.tdata:
                                yield 'tdata not OK:'
                                json_compare(mpfile_single.tdata, mpfile_single_cmp.tdata)
                            # check structural data
                            structures_ok = True
                            for name, s1 in mpfile_single.sdata[mp_cat_id].iteritems():
                                s2 = mpfile_single_cmp.sdata[mp_cat_id][name]
                                if s1 != s2:
                                    if len(s1) != len(s2):
                                        yield 'different number of sites: {} -> {}!<br>'.format(
                                                len(s1), len(s2))
                                        structures_ok = False
                                        break
                                    for site in s1:
                                        if site not in s2:
                                            found_inconsistency = True
                                            if not sm.fit(s1, s2):
                                                yield 'structures do not match!<br>'
                                                structures_ok = False
                                            break
                                        if not structures_ok:
                                            break
                            if not structures_ok:
                                continue
                            if not found_inconsistency:
                                # documents are not equal, but all components checked, skip contribution
                                # should not happen
                                yield 'inconsistency found but not identified!<br>'
                                continue

                    if target is not None:
                        yield 'submit ... '
                        if project is not None:
                            mpfile_single.insert_top(mp_cat_id, 'project', project)
                        cid = target.submit_contribution(mpfile_single, fmt) # uses get_string
                    mpfile_single.insert_top(mp_cat_id, 'cid', cid)
                    cid_shorts.append(cid_short)

                    if target is not None:
                        if idx < 5:
                            yield 'build ... '
                            url = target.build_contribution(cid)
                            url = '/'.join([target.preamble.rsplit('/', 1)[0], 'explorer', url])
                            yield ("OK. <a href='{}' class='btn btn-default btn-xs' " +
                                   "role='button' target='_blank'>View</a></br>").format(url)
                        else:
                            target.set_build_flag(cid, True)
                            yield 'OK (queued).</br>'
                    else:
                        if (ids is None and idx < 5) or ids is not None:
                            yield 'build ... '
                            mcb = MPContributionsBuilder(doc)
                            build_doc = mcb.build(cid)
                        else:
                            yield 'skip ... '
                            from pymatgen.util.provenance import Author
                            author = Author.parse_author(contributor)
                            build_doc = [mp_cat_id, author.name, cid_short, '']
                        yield build_doc

                        yield 'overview axes ... '
                        scope, local_axes = [], set()
                        mpfile_for_axes = MPFile.from_contribution(doc)
                        for k,v in mpfile_for_axes.hdata[mp_cat_id].iterate():
                            if v is None:
                                scope = scope[:k[0]]
                                scope.append(k[1])
                            else:
                                try:
                                    if k[0] == len(scope): scope.append(k[1])
                                    else: scope[-1] = k[1]
                                    vf = float(v) # trigger exception
                                    scope_str = '.'.join(scope)
                                    if idx == 0:
                                        axes.add(scope_str)
                                        ov_data[scope_str] = {cid_short: (vf, mp_cat_id)}
                                    else:
                                        local_axes.add(scope_str)
                                        ov_data[scope_str][cid_short] = (vf, mp_cat_id)
                                except:
                                    pass
                        if idx > 0:
                            axes.intersection_update(local_axes)
                        yield 'OK.</br>'.format(idx, cid_short)

                else:
                    yield 'wrong CID.</br>'

            mpfile_out.concat(mpfile_single)
            time.sleep(.01)

        ncontribs = len(cid_shorts)
        if target is not None:
            yield '<strong>{} contributions successfully submitted.</strong>'.format(ncontribs)
        else:
            for k in ov_data.keys():
                if k not in axes:
                    ov_data.pop(k)
            yield ov_data
            yield '<strong>{} contributions successfully processed.</strong>'.format(ncontribs)
    except:
        ex = sys.exc_info()[1]
        yield 'FAILED.</br>'
        yield unicode(ex).replace('"',"'")
        return
