from config import mp_level01_titles
from bson.objectid import ObjectId

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
        """reset all collections"""
        self.db.contributions.remove()

    def _get_mp_category_id(self, key, fake_it):
        not_fake = (not fake_it or self.fake is None)
        return key.split('--')[0] if not_fake else self.fake.random_element(
            elements=['mp-{}'.format(i) for i in range(1, 5)]
        )

    def _get_short_object_id(self, cid):
        return str(cid)[-6:]

    def query_contributions(self, crit):
        # TODO open `content` for arbitrary query
        props = [ 'collaborators', 'mp_cat_id' ]
        proj = dict((p, 1) for p in props)
        return self.db.contributions.find(crit, proj)

    def delete_contributions(self, crit):
        return self.db.contributions.remove(crit)

    def submit_contribution(self, mpfile, contributor_email, cids=None,
        fake_it=False, insert=False, project=None):
        """submit user data to `mpcontribs.contributions` collection

        Args:
        mpfile: MPFile object containing contribution data
        cids: contribution IDs, None if new contribution else update/replace
        """
        # apply general level-0 section on all other level-0 sections if existent
        # TODO prepend not append to contribution
        general_title = mp_level01_titles[0]
        if general_title in mpfile.document:
            general_data = mpfile.document.pop(general_title)
            for k in mpfile.document:
                mpfile.document[k].rec_update({general_title: general_data})
        # check whether length of cids and mpfile.document match
        # TODO shouldn't be necessary once update is based on embedded `cid`
        if cids is not None and len(cids) != len(mpfile.document):
            raise ValueError("number of contribution IDs provided does not "
                             "match number of mp_cat_id's in MPFile!")
        # treat every mp_cat_id as separate database insert
        contributions = []
        for idx,(k,v) in enumerate(mpfile.document.iteritems()):
            # identifiers
            mp_cat_id = self._get_mp_category_id(k, fake_it)
            cid = ObjectId() if cids is None else cids[idx] # new vs update
            cid_short = self._get_short_object_id(cid)
            # check contributor permissions if update mode
            collaborators = [contributor_email]
            if cids is not None:
                collaborators = self.db.contributions.find_one(
                    {'_id': cid}, {'collaborators': 1}
                )['collaborators']
                if contributor_email not in collaborators: raise ValueError(
                    "Submission stopped: update of contribution {} not "
                    "allowed due to insufficient permissions of {}! Ask "
                    "someone of {} to make you a collaborator on {}.".format(
                        cid_short, contributor_email, collaborators, cid_short))
            # prepare document
            doc = {'collaborators': collaborators,
                   'mp_cat_id': mp_cat_id, 'content': v}
            if project is not None: doc['project'] = project
            if insert:
                print 'submitting contribution #{} ...'.format(cid_short)
                self.db.contributions.find_and_modify({'_id': cid}, doc, upsert=True)
                contributions.append(cid)
            else:
                contributions.append(doc)
        return contributions

    def fake_multiple_contributions(self, num_contributions=20, insert=False):
        """fake the submission of many contributions"""
        if self.fake is None:
            print 'Install fake-factory to fake submissions'
            return 'Nothing done.'
        from fake.v1 import MPFakeFile
        for n in range(num_contributions):
            f = MPFakeFile(usable=True, main_general=self.fake.pybool())
            mpfile = f.make_file()
            contributor = '%s <%s>' % (self.fake.name(), self.fake.email())
            self.submit_contribution(
                mpfile, contributor, fake_it=True, insert=insert
            )
