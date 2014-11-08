from pymatgen.matproj.snl import Author
from pymongo import MongoClient
from monty.serialization import loadfn
import json, os, logging
import pandas as pd
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'
import plotly.plotly as py

class MPContributionsBuilder():
    """build user contributions from `mg_core_*.contributions`"""
    def __init__(self, db_yaml='materials_db_dev.yaml'):
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        client[config['db']].authenticate(
            config['username'], config['password']
        )
        self.contrib_coll = client[config['db']].contributions
        self.mat_coll = client[config['db']].materials
        self.pipeline = [
            { '$group': {
                '_id': '$mp_cat_id',
                'num_contribs': { '$sum': 1 },
                'contrib_ids': { '$addToSet': '$contribution_id' }
            }}
        ]

    def flatten_dict(self, dd, separator='.', prefix=''):
        """http://stackoverflow.com/a/19647596"""
        return { prefix + separator + k if prefix else k : v
                for kk, vv in dd.items()
                for k, v in self.flatten_dict(vv, separator, kk).items()
               } if isinstance(dd, dict) else { prefix : dd }

    def plot(self, cid):
        """make default plot for contribution_id"""
        plot_contrib = self.contrib_coll.find_one(
            {'contribution_id': cid}, {
                'content.data': 1, 'content.plots.default': 1,
                '_id': 0, 'contributor_email': 1
            }
        )
        if 'data' not in plot_contrib['content']:
            return None
        author = Author.parse_author(plot_contrib['contributor_email'])
        #project = str(author.name).translate(None, '.').replace(' ','_')
        fig, ax = plt.subplots(1, 1)
        plotopts = plot_contrib['content']['plots']['default']
        data = plot_contrib['content']['data']
        pd.DataFrame.from_dict(data).plot(ax=ax, **plotopts)
        return py.plot_mpl(fig, filename='test%d' % cid, auto_open=False)

    def _reset(self):
        """remove `contributed_data` keys from all documents"""
        logging.info(self.mat_coll.update(
            {'contributed_data': {'$exists': 1}},
            {'$unset': {'contributed_data': 1}},
            multi=True
        ))

    def build(self):
        """update materials collection with contributed data"""
        # NOTE: this build is only for contributions tagged with mp-id
        # TODO: in general, distinguish mp cat's by format of mp_cat_id
        plot_cids = None
        for doc in self.contrib_coll.aggregate(self.pipeline, cursor={}):
            if plot_cids is None and doc['num_contribs'] > 2:
                # only make plots for one mp-id due to plotly restrictions
                plot_cids = doc['contrib_ids']
            for cid in doc['contrib_ids']:
                tree_contrib = self.contrib_coll.find_one(
                    {'contribution_id': cid}, {
                        'content.data': 0, 'content.plots': 0, '_id': 0
                    }
                )
                author = Author.parse_author(tree_contrib['contributor_email'])
                project = str(author.name).translate(None, '.')
                tree_keys = self.flatten_dict(tree_contrib['content']).keys()
                logging.info(doc['_id'])
                logging.info(self.mat_coll.update(
                    {'task_id': doc['_id']}, { '$set': {
                        'contributed_data.%s.tree_keys' % project: tree_keys,
                        'contributed_data.%s.tree_data' % project: tree_contrib['content']
                    }}
                ))
                if plot_cids is not None and cid in plot_cids:
                    plotly_url = self.plot(cid)
                    if plotly_url is not None:
                        logging.info(self.mat_coll.update(
                            {'task_id': doc['_id']}, { '$push': {
                                'contributed_data.%s.plotly_urls' % project: plotly_url
                            }}
                        ))
