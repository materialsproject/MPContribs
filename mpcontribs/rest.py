from config import mp_level01_titles
from bson.objectid import ObjectId
from utils import get_short_object_id
from datetime import datetime

class ContributionMongoAdapter(object):
    """adapter/interface for user contributions"""
    def __init__(self, db=None):
        self.db = db
        try:
            from faker import Faker
            self.fake = Faker()
        except:
            self.fake = None

    @classmethod
    def from_config(cls, db_yaml='mpcontribs_db.yaml'):
        import os
        from pymongo import MongoClient
        from monty.serialization import loadfn
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return ContributionMongoAdapter(db)

    def _reset(self):
        self.db.contributions.remove()
        self.db.materials.remove()
        self.db.compositions.remove()

    #def _get_mp_category_id(self, key, fake_it):
    #    not_fake = (not fake_it or self.fake is None)
    #    return key.split('--')[0] if not_fake else self.fake.random_element(
    #        elements=['mp-{}'.format(i) for i in range(1, 5)]
    #    )

    def query_contributions(self, crit):
        # TODO open `content` for arbitrary query
        props = [ 'collaborators', 'mp_cat_id' ]
        proj = dict((p, 1) for p in props)
        return self.db.contributions.find(crit, proj)

    def delete_contributions(self, crit):
        return self.db.contributions.remove(crit)

    def submit_contribution(self, mpfile, contributor_email, project=None):
        """submit a single contribution to `mpcontribs.contributions` collection"""
        mp_cat_id = mpfile.document.keys()[0]
        data = mpfile.document[mp_cat_id]
        update, cid = False, ObjectId() # TODO: new vs update
        if 'test_index' in data:
            test_index = int(data['test_index'])
            cid = ObjectId.from_datetime(datetime.fromordinal(test_index))
        cid_short = get_short_object_id(cid)
        collaborators = [contributor_email]
        if update: # check contributor permissions if update mode
            collaborators = self.db.contributions.find_one(
                {'_id': cid}, {'collaborators': 1}
            )['collaborators']
            if contributor_email not in collaborators: raise ValueError(
                "Submission stopped: update of contribution #{} not "
                "allowed due to insufficient permissions of {}! Ask "
                "someone of {} to make you a collaborator on #{}.".format(
                    cid_short, contributor_email, collaborators, cid_short))
        # prepare document
        doc = { 'collaborators': collaborators, 'mp_cat_id': mp_cat_id, 'content': data }
        if project is not None: doc['project'] = project
        if self.db is None:
            doc['_id'] = cid
            return doc
        self.db.contributions.find_and_modify({'_id': cid}, doc, upsert=True)
        return cid

    #def fake_multiple_contributions(self, num_contributions=20):
    #    """fake the submission of many contributions"""
    #    if self.fake is None:
    #        print 'Install fake-factory to fake submissions'
    #        return 'Nothing done.'
    #    from fake.v1 import MPFakeFile
    #    for n in range(num_contributions):
    #        f = MPFakeFile(usable=True, main_general=self.fake.pybool())
    #        mpfile = f.make_file()
    #        contributor = '%s <%s>' % (self.fake.name(), self.fake.email())
    #        self.submit_mpfile(mpfile, contributor, fake_it=True)
