# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import bson, six
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import get_short_object_id

class ContributionMongoAdapter(object):
    """adapter/interface for user contributions"""
    def __init__(self, db=None):
        self.db = db
        if self.db is not None:
            opts = bson.CodecOptions(document_class=RecursiveDict)
            self.provenances = self.db.provenances.with_options(codec_options=opts)
            self.contributions = self.db.contributions.with_options(codec_options=opts)
            self.materials = self.db.materials.with_options(codec_options=opts)
            self.compositions = self.db.compositions.with_options(codec_options=opts)

    @classmethod
    def from_config(cls, db_yaml='mpcontribs_db.yaml'):
        import os
        from pymongo import MongoClient
        from monty.serialization import loadfn
        db_loc = os.environ.get('DB_LOC', '')
        config_path = os.path.join(db_loc, db_yaml)
        if os.path.exists(config_path):
            config = loadfn(config_path)
            client = MongoClient(
                config['host'], config['port'],
                j=False, document_class=RecursiveDict
            )
            db = client[config['db']]
            db.authenticate(config['username'], config['password'])
        else:
            client = MongoClient(j=False, document_class=RecursiveDict)
            db = client['mpcontribs']
        return ContributionMongoAdapter(db)

    def _reset(self):
        self.db.contributions.remove()
        self.db.materials.remove()
        self.db.compositions.remove()

    def query_contributions(self, crit, projection=None, collection='contributions', limit=0, sort=None):
        # TODO be careful with SON for order in crit
        coll = getattr(self, collection)
        props = None
        if projection is None:
          if collection == 'contributions':
            props = [ 'collaborators', 'identifier', 'project' ]
          elif collection == 'materials' or collection == 'compositions':
            limit = 1
        elif collection == 'contributions':
            props = [k for k,v in projection.iteritems() if v] + ['collaborators']
        projection = dict((p, 1) for p in props) if props else None
        if '_id' in crit:
            if isinstance(crit['_id'], dict):
                if '$in' in crit['_id']:
                    crit['_id']['$in'] = map(bson.ObjectId, crit['_id']['$in'])
                elif '$gt' in crit['_id'] and isinstance(crit['_id']['$gt'], six.string_types):
                    crit['_id']['$gt'] = bson.ObjectId(crit['_id']['$gt'])
            elif isinstance(crit['_id'], six.string_types):
                crit['_id'] = bson.ObjectId(crit['_id'])
        cursor = coll.find(crit, projection=projection, limit=limit)
        # TODO first sort then limit??
        #if sort is not None and isinstance(sort, dict) and 'key' in sort and 'order' in sort:
        #    return cursor.sort(sort['key'], sort['order'])
        return cursor

    def query_paginate(self, crit, projection=None, page_size=20, last_id=None, sort=None):
        # https://arpitbhayani.me/techie/fast-and-efficient-pagination-in-mongodb.html
        """Function returns `page_size` number of documents after last_id and the new last_id."""
        if last_id is not None:
            crit.update({'_id': {'$gt': last_id}})
        data = list(self.query_contributions(crit, projection=projection, limit=page_size, sort=sort))
        return (data, data[-1]['_id']) if data else (None, None)

    def count(self, crit, collection='contributions'):
        coll = getattr(self, collection)
        return coll.count(crit)

    def delete_contributions(self, crit):
        return self.contributions.remove(crit)

    def submit_contribution(self, mpfile, contributor_email, project=None):
        """submit a single contribution to `mpcontribs.contributions` collection"""
        if len(mpfile.document) > 1:
            raise ValueError('submission only possible for single section MPFiles')
        identifier = mpfile.document.keys()[0]
        data = mpfile.document[identifier]
        update = ('cid' in data) # new vs update
        cid = bson.ObjectId(data['cid']) if update else bson.ObjectId()
        cid_short = get_short_object_id(cid)
        collaborators = [contributor_email]
        if update and self.db is not None: # check contributor permissions if update mode
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
        doc = { 'collaborators': collaborators, 'identifier': identifier, 'content': data }
        doc['project'] = data.get('project', 'other') if project is None else project
        if self.db is None:
            doc['_id'] = cid
            return doc
        self.contributions.find_and_modify({'_id': cid}, doc, upsert=True)
        return cid
