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
    def __init__(self, db):
        self.contrib_coll = db.contributions
        self.mat_coll = db.materials
        self.pipeline = [
            { '$group': {
                '_id': '$mp_cat_id',
                'num_contribs': { '$sum': 1 },
                'contrib_ids': { '$addToSet': '$contribution_id' }
            }}
        ]

    @classmethod
    def from_config(cls, db_yaml='materials_db_dev.yaml'):
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return MPContributionsBuilder(db)

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
                'content.data': 1, 'content.plots': 1,
                '_id': 0, 'contributor_email': 1
            }
        )
        if 'data' not in plot_contrib['content']:
            return None
        author = Author.parse_author(plot_contrib['contributor_email'])
        #project = str(author.name).translate(None, '.').replace(' ','_')
        data = plot_contrib['content']['data']
        df = pd.DataFrame.from_dict(data)
        urls = []
        for nplot,plotopts in enumerate(
            plot_contrib['content']['plots'].itervalues()
        ):
            fig, ax = plt.subplots(1, 1)
            df.plot(ax=ax, **plotopts)
            urls.append(
                py.plot_mpl(fig, filename='test%d_%d' % (cid,nplot), auto_open=False)
            )
        return urls

    def _reset(self):
        """remove `contributed_data` keys from all documents"""
        logging.info(self.mat_coll.update(
            {'contributed_data': {'$exists': 1}},
            {'$unset': {'contributed_data': 1}},
            multi=True
        ))

    def build(self, cids=None):
        """update materials collection with contributed data"""
        # NOTE: this build is only for contributions tagged with mp-id
        # TODO: in general, distinguish mp cat's by format of mp_cat_id
        plot_cids = None
        for doc in self.contrib_coll.aggregate(self.pipeline, cursor={}):
            #if plot_cids is None and doc['num_contribs'] > 2:
            # only make plots for one mp-id due to plotly restrictions
            plot_cids = doc['contrib_ids']
            for cid in doc['contrib_ids']:
                if cids is not None and cid not in cids: continue
                tree_contrib = self.contrib_coll.find_one(
                    {'contribution_id': cid}, {
                        'content.data': 0, 'content.plots': 0, '_id': 0
                    }
                )
                table_contrib = self.contrib_coll.find_one(
                    {'contribution_id': cid}, { 'content.data': 1, '_id': 0 }
                )
                author = Author.parse_author(tree_contrib['contributor_email'])
                project = str(author.name).translate(None, '.').replace(' ','_')
                logging.info(doc['_id'])
                all_data = {}
                if tree_contrib['content']:
                    all_data.update({
                        'contributed_data.%s.tree_data.%d' % (project, cid): tree_contrib['content'],
                    })
                if 'data' in table_contrib['content']:
                    table_columns, table_rows = None, None
                    raw_data = table_contrib['content']['data']
                    if isinstance(raw_data, dict):
                        table_columns = [ { 'title': k } for k in raw_data ]
                        table_rows = [
                            [ str(raw_data[d['title']][row_index]) for d in table_columns ]
                            for row_index in xrange(len(
                                raw_data[table_columns[0]['title']]
                            ))
                        ]
                    elif isinstance(raw_data, list):
                        table_columns = [ { 'title': k } for k in raw_data[0] ]
                        table_rows = [
                            [ str(row[d['title']]) for d in table_columns ]
                            for row in raw_data
                        ]
                    if table_columns is not None:
                        all_data.update({
                            'contributed_data.%s.tables.%d.columns' % (project,cid): table_columns,
                            'contributed_data.%s.tables.%d.rows' % (project,cid): table_rows,
                        })
                logging.info(self.mat_coll.update(
                    {'task_id': doc['_id']}, { '$set': all_data }
                ))
                if plot_cids is not None and cid in plot_cids:
                    plotly_urls = self.plot(cid)
                    if plotly_urls is not None:
                        for plotly_url in plotly_urls:
                            logging.info(self.mat_coll.update(
                                {'task_id': doc['_id']}, { '$push': {
                                    'contributed_data.%s.plotly_urls.%d' % (project,cid): plotly_url
                                }}
                            ))
