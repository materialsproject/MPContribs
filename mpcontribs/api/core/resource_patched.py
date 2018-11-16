from flask import request
from flask_restplus import Resource as OriginalResource
from flask_restplus.mask import Mask
from flask_pymongo import PyMongo
from pattern.en import singularize, pluralize

mongo = PyMongo()

class Resource(OriginalResource):
    """Resource with query methods to apply mask as MongoDB projection"""
    def __init__(self, api=None, *args, **kwargs):
        super(Resource, self).__init__(api=api, *args, **kwargs)
        class_name = singularize(self.__class__.__name__)
        model_name = class_name + 'Model'
        self.model = self.api.models[model_name]
        collection_name = pluralize(class_name.lower())
        self.collection = mongo.db[collection_name]

    def projection(self):
        mask = Mask(request.headers.get('X-Fields', self.model.__mask__))
        return None if '*' in mask.keys() else mask

    def query_one(self, criteria=None, **kwargs):
        return self.collection.find_one(
            criteria, projection=self.projection(), **kwargs
        )

    # TODO pagination?
    def query(self, criteria=None, **kwargs):
        return list(self.collection.find(
            criteria, projection=self.projection(), **kwargs
        ).limit(2)) # TODO remove limit
