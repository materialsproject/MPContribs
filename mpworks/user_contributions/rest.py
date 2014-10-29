import os
from monty.serialization import loadfn
from pymatgen.core import Structure
from pymatgen.matproj.snl import StructureNL
from mpworks.submission.submission_mongo import SubmissionMongoAdapter
from parsers import RecursiveParser

def submit_snl_from_cif(submitter_email, cif_file, metadata_file):
    """submit StructureNL via CIF and YAML MetaData files

    method to submit StructureNL object generated from CIF file via separate
    file containing MetaData in YAML format as required by the MPStructureNL
    constructor. Developed to be used for the submission of new structures
    during RSC publishing process (pilot project).

    Args:
    metadata_file: name of file parsed via monty's loadfn
    """
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


def submit_contribution(
    input_handle, contribution_id=None, parser=RecursiveParser()
):
    """submit user data to `user_contributions` database

    Args:
    input_handle: object to "connect" to input, i.e. file handle
    contribution_id: None if new contribution else update/replace
    parser: parser class to use on input handle
    """
    if not isinstance(input_handle, file):
        raise TypeError(
            'type %r not supported as input handle!' % type(input_handle)
        )
    fileExt = os.path.splitext(input_handle.name)[1][1:]
    parser.parse(input_handle.read(), fileExt=fileExt)
    return parser
