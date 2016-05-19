import os, re, bson, pandas
from itertools import groupby
from io.core.recdict import RecursiveDict
from io.core.utils import get_short_object_id, nest_dict
from config import mp_level01_titles, mp_id_pattern
from pmg_utils.author import Author

class MPContributionsBuilder():
    """build user contributions from `mpcontribs.contributions`"""
    def __init__(self, db):
        self.db = db
        if isinstance(self.db, dict):
            self.materials = RecursiveDict()
            self.compositions = RecursiveDict()
        else:
            opts = bson.CodecOptions(document_class=bson.SON)
            self.contributions = self.db.contributions.with_options(codec_options=opts)
            self.materials = self.db.materials.with_options(codec_options=opts)
            self.compositions = self.db.compositions.with_options(codec_options=opts)

    @classmethod
    def from_config(cls, db_yaml='mpcontribs_db.yaml'):
        from monty.serialization import loadfn
        from pymongo import MongoClient
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return MPContributionsBuilder(db)

    def delete(self, project, cids):
        for contrib in self.contributions.find({'_id': {'$in': cids}}):
            mp_cat_id, cid = contrib['mp_cat_id'], contrib['_id']
            is_mp_id = mp_id_pattern.match(mp_cat_id)
            coll = self.materials if is_mp_id else self.compositions
            key = '.'.join([project, str(cid)])
            coll.update({}, {'$unset': {key: 1}}, multi=True)
        # remove `project` field when no contributions remaining
        for coll in [self.materials, self.compositions]:
            for doc in coll.find({project: {'$exists': 1}}):
                for d in doc.itervalues():
                    if not d:
                        coll.update({'_id': doc['_id']}, {'$unset': {project: 1}})

    def find_contribution(self, cid):
        if isinstance(self.db, dict): return self.db
        else: return self.contributions.find_one({'_id': cid})

    def build(self, contributor_email, cid):
        """update materials/compositions collections with contributed data"""
        cid_short, cid_str = get_short_object_id(cid), str(cid)
        if isinstance(self.db, dict): cid_str = cid_short
        contrib = self.find_contribution(cid)
        if contributor_email not in contrib['collaborators']: raise ValueError(
            "Build stopped: building contribution {} not "
            "allowed due to insufficient permissions of {}! Ask "
            "someone of {} to make you a collaborator on {}.".format(
                cid_short, contributor_email, contrib['collaborators'], cid_short))
        mp_cat_id = contrib['mp_cat_id']
        is_mp_id = mp_id_pattern.match(mp_cat_id)
        self.curr_coll = self.materials if is_mp_id else self.compositions
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.') \
                if 'project' not in contrib else contrib['project']
        # TODO prepare Notebook via ExecutePreprocessor
        # update collection with tree and table data
        #if isinstance(self.db, dict):
        #    unflatten_dict(all_data)
        #    self.curr_coll.rec_update(nest_dict(all_data, [mp_cat_id]))
        #else:
        #    self.curr_coll.update({'_id': mp_cat_id}, {'$set': all_data}, upsert=True)
        #if isinstance(self.db, dict):
        #    return [
        #      mp_cat_id, project, cid_str,
        #      self.curr_coll[mp_cat_id][project][cid_str]
        #    ]
        #else:
        #    return '{}/{}/{}/{}'.format( # return URL for contribution page
        #        ('materials' if is_mp_id else 'compositions'),
        #        mp_cat_id, project, cid_str)
