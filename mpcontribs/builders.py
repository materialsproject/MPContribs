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
        if isinstance(self.db, dict):
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
        url_list = [] if isinstance(self.db, dict) else list(self.curr_coll.find(
            {subfld: {'$exists': True}}, {subfld: 1}
        ))
        urls = url_list[0][project][cid]['plotly_urls'] if len(url_list) else []
        for nplot,plotopts in enumerate(contrib['content']['plots'].itervalues()):
            filename = '{}_{}_{}'.format(
                ('viewer' if isinstance(self.db, dict) else 'mp'), cid, nplot)
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

    def delete(self, project, cids):
        for contrib in self.db.contributions.find({'_id': {'$in': cids}}):
            mp_cat_id, cid = contrib['mp_cat_id'], contrib['_id']
            is_mp_id = self.mp_id_pattern.match(mp_cat_id)
            coll = self.mat_coll if is_mp_id else self.comp_coll
            key = '.'.join([project, str(cid)])
            coll.update({}, {'$unset': {key: 1}}, multi=True)
        # remove `project` field when no contributions remaining
        for coll in [self.mat_coll, self.comp_coll]:
            for doc in coll.find({project: {'$exists': 1}}):
                for d in doc.itervalues():
                    if not d:
                        coll.update({'_id': doc['_id']}, {'$unset': {project: 1}})

    def find_contribution(self, cid):
        if isinstance(self.db, dict): return self.db
        else: return self.db.contributions.find_one({'_id': cid})

    def build(self, contributor_email, cid):
        """update materials/compositions collections with contributed data"""
        cid_short, cid_str = get_short_object_id(cid), str(cid)
        contrib = self.find_contribution(cid)
        mp_cat_id = contrib['mp_cat_id']
        is_mp_id = self.mp_id_pattern.match(mp_cat_id)
        self.curr_coll = self.mat_coll if is_mp_id else self.comp_coll
        if contributor_email not in contrib['collaborators']: raise ValueError(
            "Build stopped: building contribution {} not "
            "allowed due to insufficient permissions of {}! Ask "
            "someone of {} to make you a collaborator on {}.".format(
                cid_short, contributor_email, contrib['collaborators'], cid_short))
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
        if isinstance(self.db, dict):
            unflatten_dict(all_data)
            self.curr_coll.rec_update(nest_dict(all_data, [mp_cat_id]))
        else:
            self.curr_coll.update({'_id': mp_cat_id}, {'$set': all_data}, upsert=True)
        # interactive graphs
        plotly_urls = self.plot(contributor_email, contrib)
        if plotly_urls is not None:
            if isinstance(self.db, dict):
                unflatten_dict(plotly_urls)
                self.curr_coll.rec_update(nest_dict(plotly_urls, [mp_cat_id]))
            else:
                self.curr_coll.update({'_id': mp_cat_id}, {'$set': plotly_urls})
        if isinstance(self.db, dict):
            return self.curr_coll
        else:
            return '{}/{}/contributions/{}'.format( # return URL for contribution page
                ('materials' if is_mp_id else 'compositions'),
                mp_cat_id, cid_short) # TODO: implement on frontend, short cid sufficient?
