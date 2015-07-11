import os
from collections import namedtuple
from six import string_types

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


