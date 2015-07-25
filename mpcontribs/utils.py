from __future__ import unicode_literals, print_function
import os, re, pwd
from collections import namedtuple
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
    from mpcontribs.io.mpfile import MPFile
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
        if test: mpfile_single.set_test_mode(mp_cat_id, idx)
        print('submit contribution for {} ...'.format(mp_cat_id))
        if target is not None:
            mpfile_single.write_file('tmp')
            cid = target.submit_contribution('tmp')
            os.remove('tmp')
            cid_short = get_short_object_id(cid)
        else:
            doc = cma.submit_contribution(mpfile_single, contributor)
            cid = doc['_id']
            cid_short = get_short_object_id(cid)
        print('> submitted as #{}'.format(cid_short))
        mpfile_single.insert_id(mp_cat_id, cid)
        cid_shorts.append(cid_short)
        mpfile.concat(mpfile_single)
        print('> build contribution #{} into {} ...'.format(cid_short, mp_cat_id))
        if target is not None:
            url = target.build_contribution(cid)
            print('> built #{}, see {}/{}'.format(cid_short, SITE, url))
        else:
            mcb = MPContributionsBuilder(doc)
            single_build_doc = mcb.build(contributor, cid)
            build_doc.rec_update(single_build_doc)
            print('> built #{}'.format(cid_short))
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

# from pymatgen.matproj.snl
class Author(namedtuple('Author', ['name', 'email'])):
    """
    An Author contains two fields:

    .. attribute:: name

        Name of author (String)

    .. attribute:: email

        Email of author (String)
    """

    def __str__(self):
        """String representation of an Author"""
        return '{} <{}>'.format(self.name, self.email)

    def as_dict(self):
        return {"name": self.name, "email": self.email}

    @staticmethod
    def from_dict(d):
        return Author(d['name'], d['email'])

    @staticmethod
    def parse_author(author):
        """
        Parses an Author object from either a String, dict, or tuple

        Args:
            author: A String formatted as "NAME <email@domain.com>",
                (name, email) tuple, or a dict with name and email keys.

        Returns:
            An Author object.
        """
        if isinstance(author, string_types):
            # Regex looks for whitespace, (any name), whitespace, <, (email),
            # >, whitespace
            m = re.match('\s*(.*?)\s*<(.*?@.*?)>\s*', author)
            if not m or m.start() != 0 or m.end() != len(author):
                raise ValueError("Invalid author format! {}".format(author))
            return Author(m.groups()[0], m.groups()[1])
        elif isinstance(author, dict):
            return Author.from_dict(author)
        else:
            if len(author) != 2:
                raise ValueError("Invalid author, should be String or (name, "
                                 "email) tuple: {}".format(author))
            return Author(author[0], author[1])


# kept for historic reasons
def submit_snl_from_cif(submitter_email, cif_file, metadata_file):
    """submit StructureNL via CIF and YAML MetaData files

    method to submit StructureNL object generated from CIF file via separate
    file containing MetaData in YAML format as required by the MPStructureNL
    constructor. Developed to be used for the submission of new structures
    during RSC publishing process (pilot project).

    Args:
    metadata_file: name of file parsed via monty's loadfn
    """
    from mpworks.submission.submission_mongo import SubmissionMongoAdapter
    from monty.serialization import loadfn
    from pymatgen.core import Structure
    from pymatgen.matproj.snl import StructureNL
    sma = SubmissionMongoAdapter.auto_load()
    pth = os.path.dirname(os.path.realpath(__file__))
    structure = Structure.from_file(os.path.join(pth, cif_file))
    config = loadfn(os.path.join(pth, metadata_file))
    if not config['references'].startswith('@'):
        config['references'] = open(
            os.path.join(pth, config['references']),'r'
        ).read()
    snl = StructureNL(structure, **config)
    sma.submit_snl(snl, submitter_email)


