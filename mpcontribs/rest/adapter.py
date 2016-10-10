import bson
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from mpcontribs.io.core.utils import get_short_object_id
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
        if not self.db is None:
            opts = bson.CodecOptions(document_class=bson.SON)
            self.contributions = self.db.contributions.with_options(codec_options=opts)
            self.materials = self.db.materials.with_options(codec_options=opts)
            self.compositions = self.db.compositions.with_options(codec_options=opts)

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

    def query_contributions(self, crit, projection=None, collection='contributions'):
        # TODO be careful with SON for order in crit
        coll = getattr(self, collection)
        limit, props = 0, None
        if projection is None:
          if collection == 'contributions':
            props = [ 'collaborators', 'mp_cat_id', 'project' ]
          elif collection == 'materials' or collection == 'compositions':
            limit = 1
        elif collection == 'contributions':
            props = [k for k,v in projection.iteritems() if v] + ['collaborators']
        projection = dict((p, 1) for p in props) if props else None
        return coll.find(crit, projection=projection, limit=limit)

    def delete_contributions(self, crit):
        return self.contributions.remove(crit)

    def submit_contribution(self, mpfile, contributor_email, project=None):
        """submit a single contribution to `mpcontribs.contributions` collection"""
        if len(mpfile.document) > 1:
            raise ValueError('submission only possible for single section MPFiles')
        mp_cat_id = mpfile.document.keys()[0]
        data = mpfile.document[mp_cat_id]
        update = ('cid' in data) # new vs update
        cid = bson.ObjectId(data['cid']) if update else bson.ObjectId()
        cid_short = get_short_object_id(cid)
        collaborators = [contributor_email]
        if update: # check contributor permissions if update mode
            data.pop('cid')
            collaborators = self.contributions.find_one(
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
        self.contributions.find_and_modify({'_id': cid}, doc, upsert=True)
        return cid

    #def fake_multiple_contributions(self, num_contributions=20):
    #    """fake the submission of many contributions"""
    #    if self.fake is None:
    #        print 'Install fake-factory to fake submissions'
    #        return 'Nothing done.'
    #    from mpcontribs.fake.v1 import MPFakeFile
    #    for n in range(num_contributions):
    #        f = MPFakeFile(usable=True, main_general=self.fake.pybool())
    #        mpfile = f.make_file()
    #        contributor = '%s <%s>' % (self.fake.name(), self.fake.email())
    #        self.submit_mpfile(mpfile, contributor, fake_it=True)
