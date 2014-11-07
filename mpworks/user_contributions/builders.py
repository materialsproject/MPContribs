from pymatgen.matproj.snl import Author
from pymongo import MongoClient
import json, sys
import pandas as pd
import matplotlib.pyplot as plt
#pd.options.display.mpl_style = 'default'
import plotly.plotly as py

host, port, db_name = 'localhost', 27019, 'user_contributions'
username, password = 'test', 'test'
client = MongoClient(host, port, j=False)
client[db_name].authenticate(username, password)
contrib_coll = client[db_name].contributions
mat_coll = client[db_name].materials

# http://stackoverflow.com/a/19647596
def flatten_dict(dd, separator='_', prefix=''):
    return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_dict(vv, separator, kk).items()
           } if isinstance(dd, dict) else { prefix : dd }

def plot(cid):
    """make default plot for contribution_id"""
    plot_contrib = contrib_coll.find_one(
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

if __name__ == '__main__':
    # NOTE: distinguish mp cat's by format of mp_cat_id
    pipeline = [
        { '$group': {
            '_id': '$mp_cat_id',
            'num_contribs': { '$sum': 1 },
            'contrib_ids': { '$addToSet': '$contribution_id' }
        }}
    ]
    plot_cids = None
    for doc in contrib_coll.aggregate(pipeline, cursor={}):
        if plot_cids is None and doc['num_contribs'] > 2:
            plot_cids = doc['contrib_ids']
        for cid in doc['contrib_ids']:
            tab_contrib = contrib_coll.find_one(
                {'contribution_id': cid}, {
                    'content.data': 0, 'content.plots': 0, '_id': 0
                }
            )
            author = Author.parse_author(tab_contrib['contributor_email'])
            project = str(author.name).translate(None, '.')
            tabular_data = flatten_dict(tab_contrib)
            mat_coll.update(
                {'task_id': doc['_id']}, { '$set': {
                    'external_data.%s.tabular_data' % project: tabular_data
                }}
            )
            if plot_cids is not None and cid in plot_cids:
                plotly_url = plot(cid)
                if plotly_url is not None:
                    mat_coll.update(
                        {'task_id': doc['_id']}, { '$push': {
                            'external_data.%s.plotly_urls' % project: plotly_url
                        }}
                    )
            print doc['_id']
