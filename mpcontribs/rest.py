import os, logging
from monty.serialization import loadfn
import datetime
from StringIO import StringIO
from config import mp_level01_titles

class ContributionMongoAdapter(object):
    """adapter/interface for user contributions"""
    def __init__(self, db=None):
        self.db = db
        if self.db is None:
            self.current_contribution_id = 0
        try:
            from faker import Faker
            self.fake = Faker()
        except:
            self.fake = None

    @classmethod
    def from_config(cls, db_yaml='mpcontribs_db.yaml'):
        from pymongo import MongoClient
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return ContributionMongoAdapter(db)

    def _reset(self):
        """reset all collections"""
        self.db.id_assigner.remove()
        self.db.contributions.remove()
        self.db.materials.remove()
        self.db.id_assigner.insert({'next_contribution_id': 1})

    def _get_next_contribution_id(self):
        """get the next contribution id"""
        if self.db is None:
            self.current_contribution_id += 1
            return self.current_contribution_id
        else:
            return self.db.id_assigner.find_and_modify(
                update={'$inc': {'next_contribution_id': 1}}
            )['next_contribution_id']

    def _get_available_mp_ids(self):
        available_mp_ids = []
        for doc in self.db.materials.aggregate([
            { '$project': { 'task_id': 1, '_id': 0 } },
            { '$match':  { 'task_id': { '$regex': '^mp-[0-9]{1}$' } } },
        ], cursor={}):
            available_mp_ids.append(doc['task_id'])
        if len(available_mp_ids) == 0:
            raise ValueError('No mp_ids available! Check DB connection!')
        return available_mp_ids

    def query_contributions(self, crit):
        props = [ '_id', 'collaborators', 'mp_cat_id', 'contribution_id' ]
        proj = dict((p, int(p!='_id')) for p in props)
        return self.db.contributions.find(crit, proj)

    def delete_contributions(self, crit):
        return self.db.contributions.remove(crit)

    def submit_contribution(self, mpfile, contributor_email, cids=None,
        fake_it=False, insert=False, project=None):
        """submit user data to `materials.contributions` collection

        Args:
        mpfile: MPFile object containing contribution data
        cids: contribution IDs, None if new contribution else update/replace
        """
        # apply general level-0 section on all other level-0 sections if existent
        general_title = mp_level01_titles[0]
        if general_title in mpfile.document:
            general_data = mpfile.document.pop(general_title)
            for k in mpfile.document:
                mpfile.document[k].rec_update({general_title: general_data})
        # check whether length of cids and mpfile.document match
        if cids is not None and len(cids) != len(mpfile.document):
            raise ValueError("number of contribution IDs provided does not "
                             "match number of mp_cat_id's in MPFile!")
        # treat every mp_cat_id as separate database insert
        contributions = []
        for idx,(k,v) in enumerate(mpfile.document.iteritems()):
            mp_cat_id = k.split('--')[0] if not fake_it or self.fake is None else \
                    self.fake.random_element(elements=self._get_available_mp_ids())
            # new submission vs update
            cid = self._get_next_contribution_id() if cids is None else cids[idx]
            # check contributor permissions if update mode
            collaborators = [contributor_email]
            if cids is not None:
                collaborators = self.db.contributions.find_one(
                    {'contribution_id': cid}, {'_id': 0, 'collaborators': 1}
                )['collaborators']
                if contributor_email not in collaborators:
                    raise ValueError(
                        "Submission stopped: update of contribution {} not"
                        " allowed due to insufficient permissions of {}!"
                        " Ask someone of {} to make you a collaborator on"
                        " contribution {}.".format(
                            cid, contributor_email, collaborators, cid
                        ))
            # prepare document
            doc = {
                'collaborators': collaborators,
                'contribution_id': cid,
                'contributed_at': datetime.datetime.utcnow().isoformat(),
                'mp_cat_id': mp_cat_id, 'content': v
            }
            if project is not None: doc['project'] = project
            if insert:
                logging.info('inserting {} ...'.format(doc['contribution_id']))
                #self.db.contributions.replace_one({'contribution_id': cid}, doc, upsert=True)
                self.db.contributions.find_and_modify({'contribution_id': cid}, doc, upsert=True)
                contributions.append(doc['contribution_id'])
            else:
                contributions.append(doc)
        return contributions

    def fake_multiple_contributions(self, num_contributions=20, insert=False):
        """fake the submission of many contributions"""
        if self.fake is None:
            logging.info("Install fake-factory to fake submissions")
            return 'Nothing done.'
        from fake.v1 import MPFakeFile
        for n in range(num_contributions):
            f = MPFakeFile(usable=True, main_general=self.fake.pybool())
            mpfile = f.make_file()
            contributor = '%s <%s>' % (self.fake.name(), self.fake.email())
            logging.info(self.submit_contribution(
                mpfile, contributor, fake_it=True, insert=insert
            ))
