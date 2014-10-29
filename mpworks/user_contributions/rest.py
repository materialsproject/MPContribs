import os, datetime
from monty.serialization import loadfn
from pymatgen.core import Structure
from pymatgen.matproj.snl import StructureNL
from mpworks.submission.submission_mongo import SubmissionMongoAdapter
from parsers import RecursiveParser
from pymongo import MongoClient

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

def create_db(host='localhost', port=27017, db_name='user_contributions'):
    """create database and add user for testing"""
    client = MongoClient(host, port, j=True)
    client.drop_database(db_name)
    client[db_name].add_user('test', 'test', read_only=False)


class ContributionMongoAdapter(object):
    """adapter/interface for user contributions"""
    def __init__(
        self, host='localhost', port=27017, db_name='user_contributions',
        username='test', password='test'
    ):
        client = MongoClient(host, port, j=False)
        client[db_name].authenticate(username, password)
        self.id_assigner = client[db_name].id_assigner
        self.contributions = client[db_name].contributions

    def _reset(self):
        """reset all collections"""
        self.contributions.remove()
        self.id_assigner.remove()
        self.id_assigner.insert({'next_contribution_id': 1})

    def _get_next_contribution_id(self):
        """get the next contribution id"""
        return self.id_assigner.find_and_modify(
            update={'$inc': {'next_contribution_id': 1}}
        )['next_contribution_id']

    def submit_contribution(
        self, input_handle, contributor_email, contribution_id=None,
        parser=RecursiveParser()
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
        # TODO: implement update/replace based on contribution_id=None
        doc = {
            'contributor_email': contributor_email,
            'contribution_id': self._get_next_contribution_id(),
            'contributed_at': datetime.datetime.utcnow().isoformat(),
            'contribution_data': parser.document
        }
        self.contributions.insert(doc)
        return parser # TODO: return contribution id
