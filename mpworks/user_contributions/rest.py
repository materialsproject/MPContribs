import os
from monty.serialization import loadfn
from pymatgen.core import Structure
from pymatgen.matproj.snl import StructureNL
from mpworks.submission.submission_mongo import SubmissionMongoAdapter

def submit_snl_from_cif(submitter_email, cif_file, metadata_file):
    """
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
