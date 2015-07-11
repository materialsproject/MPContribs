import os, re
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'
import plotly.plotly as py
from plotly.graph_objs import *
from itertools import groupby
from io.utils import nest_dict, RecursiveDict
from config import mp_level01_titles
from utils import Author, get_short_object_id, unflatten_dict

class MPContributionsBuilder():
    """build user contributions from `mpcontribs.contributions`"""
    def __init__(self, db):
        self.mp_id_pattern = re.compile('mp-\d+', re.IGNORECASE)
        self.db = db
        if isinstance(self.db, list):
            self.mat_coll = RecursiveDict()
            self.comp_coll = RecursiveDict()
        else:
            self.mat_coll = db.materials
            self.comp_coll = db.compositions

    @classmethod
    def from_config(cls, db_yaml='mpcontribs_db.yaml'):
        from monty.serialization import loadfn
        from pymongo import MongoClient
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return MPContributionsBuilder(db)

    def plot(self, contributor_email, contrib):
        """make all plots for contribution"""
        if not any([
          key.startswith(mp_level01_titles[1]+'_') for key in contrib['content']
        ]): return None
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.').replace(' ','_') \
                if 'project' not in contrib else contrib['project']
        cid = str(contrib['_id'])
        subfld = '{}.{}.plotly_urls'.format(project, cid)
        url_list = [] if isinstance(self.db, list) else list(self.curr_coll.find(
            {subfld: {'$exists': True}}, {subfld: 1}
        ))
        urls = url_list[0][project][cid]['plotly_urls'] if len(url_list) else []
        for nplot,plotopts in enumerate(contrib['content']['plots'].itervalues()):
            filename = '{}_{}_{}'.format(
                ('viewer' if isinstance(self.db, list) else 'mp'), cid, nplot)
            fig, ax = plt.subplots(1, 1)
            table_name = plotopts.pop('table')
            data = contrib['content'][table_name]
            df = pd.DataFrame.from_dict(data)
            df.plot(ax=ax, **plotopts)
            if len(urls) == len(contrib['content']['plots']):
                pyfig = py.get_figure(urls[nplot])
                for ti,line in enumerate(ax.get_lines()):
                    pyfig['data'][ti]['x'] = list(line.get_xdata())
                    pyfig['data'][ti]['y'] = list(line.get_ydata())
                py.plot(pyfig, filename=filename, auto_open=False)
            else:
                update = dict(layout=dict(
                    annotations=[dict(text=' ')],
                    showlegend=True,
                    legend=Legend(x=1.05, y=1)
                ))
                urls.append(py.plot_mpl(
                    fig, filename=filename, auto_open=False,
                    strip_style=True, update=update, resize=True
                ))
        plotly_urls = RecursiveDict({subfld: urls})
        return None if len(url_list) else plotly_urls

    def delete(self, cids):
        for coll in [self.mat_coll, self.comp_coll]:
            unset_dict = {}
            for doc in coll.find():
                for project,d in doc.iteritems():
                    for cid in d:
                        if cid not in cids: continue
                        unset_dict['.'.join([project, cid])] = 1
            if len(unset_dict):
                coll.update({}, {'$unset': unset_dict}, multi=True)
            # remove `project` field when no contributions remaining
            for doc in coll.find():
                for project,d in doc.iteritems():
                    if not d:
                        coll.update({'_id': doc['_id']}, {'$unset': {project: 1}})

    def find_contribution(self, cid):
        if isinstance(self.db, list):
            for doc in self.db:
                if doc['_id'] == cid: return doc
        else:
            return self.db.contributions.find_one({'_id': cid})

    def get_contribution_groups(self):
        if isinstance(self.db, list):
            contribution_groups = []
            for key,group in groupby(db, lambda item: item['mp_cat_id']):
                grp = list(group)
                contribution_groups.append({
                    '_id': key, 'num_contribs': len(grp),
                    'contrib_ids': [ el['_id'] for el in grp ]
                })
        else:
            contribution_groups = self.db.contributions.aggregate([
                { '$group': {
                    '_id': '$mp_cat_id',
                    'num_contribs': { '$sum': 1 },
                    'contrib_ids': { '$addToSet': '$_id' }
                }}
            ], cursor={})
        return contribution_groups

    def build(self, contributor_email, cids=None):
        """update materials/compositions collections with contributed data"""
        # TODO check all DB calls, consolidate in aggregation call?
        for doc in self.get_contribution_groups():
            for cid in doc['contrib_ids']:
                if cids is not None and cid not in cids: continue
                # identifiers, contributor check, project
                cid_short, cid_str = get_short_object_id(cid), str(cid)
                contrib = self.find_contribution(cid)
                if contributor_email not in contrib['collaborators']: raise ValueError(
                    "Build stopped: building contribution {} not "
                    "allowed due to insufficient permissions of {}! Ask "
                    "someone of {} to make you a collaborator on {}.".format(
                        cid_short, contributor_email, contrib['collaborators'], cid_short))
                print 'building #{} into {} ...'.format(cid_short, doc['_id'])
                author = Author.parse_author(contributor_email)
                project = str(author.name).translate(None, '.').replace(' ','_') \
                        if 'project' not in contrib else contrib['project']
                # prepare tree and table data
                all_data = RecursiveDict()
                for key,value in contrib['content'].iteritems():
                    if key == 'plots' or key.startswith(mp_level01_titles[1]+'_'): continue
                    all_data.rec_update(nest_dict(
                        value, ['{}.{}.tree_data'.format(project, cid_str), key]
                    ))
                if 'plots' in contrib['content']:
                    # TODO also include non-default tables (multiple tables support)
                    table_columns, table_rows = None, None
                    table_name = contrib['content']['plots']['default']['table']
                    raw_data = contrib['content'][table_name]
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
                        all_data.rec_update({
                            '{}.{}.tables.columns'.format(project, cid_str): table_columns,
                            '{}.{}.tables.rows'.format(project, cid_str): table_rows,
                        })
                # update collection with tree and table data
                is_mp_id = self.mp_id_pattern.match(doc['_id'])
                self.curr_coll = self.mat_coll if is_mp_id else self.comp_coll
                if isinstance(self.db, list):
                    unflatten_dict(all_data)
                    self.curr_coll.rec_update(nest_dict(all_data, [doc['_id']]))
                else:
                    self.curr_coll.update({'_id': doc['_id']}, {'$set': all_data}, upsert=True)
                # interactive graphs
                plotly_urls = self.plot(contributor_email, contrib)
                if plotly_urls is not None:
                    if isinstance(self.db, list):
                        unflatten_dict(plotly_urls)
                        self.curr_coll.rec_update(nest_dict(plotly_urls, [doc['_id']]))
                    else:
                        self.curr_coll.update({'_id': doc['_id']}, {'$set': plotly_urls})
