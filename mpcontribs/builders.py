import os, re, bson, pandas
from itertools import groupby
from io.core.recdict import RecursiveDict
from io.core.utils import get_short_object_id, nest_dict
from config import mp_level01_titles, mp_id_pattern
from pmg_utils.author import Author

def flatten_dict(dd, separator='.', prefix=''):
    """http://stackoverflow.com/a/19647596"""
    return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_dict(vv, separator, kk).items()
           } if isinstance(dd, dict) else { prefix : dd }

def unflatten_dict(d):
    for k in d:
        value, keys = d.pop(k), k.split('.')
        d.rec_update(nest_dict({keys[-1]: value}, keys[:-1]))

class MPContributionsBuilder():
    """build user contributions from `mpcontribs.contributions`"""
    def __init__(self, db):
        self.db = db
        if isinstance(self.db, dict):
            self.materials = RecursiveDict()
            self.compositions = RecursiveDict()
        else:
            import plotly.plotly as py
            import cufflinks
            cufflinks.set_config_file(world_readable=True, theme='pearl')
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

    def plot(self, contributor_email, contrib):
        """make all plots for contribution"""
        if not any([
          key.startswith(mp_level01_titles[1]) for key in contrib['content']
        ]): return None
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.') \
                if 'project' not in contrib else contrib['project']
        cid = str(contrib['_id'])
        if isinstance(self.db, dict): cid = get_short_object_id(cid)
        subfld = '{}.{}.plotly_urls'.format(project, cid)
        url_list = [] if isinstance(self.db, dict) else list(self.curr_coll.find(
            {subfld: {'$exists': True}}, {subfld: 1}
        ))
        urls = url_list[0][project][cid]['plotly_urls'] if len(url_list) else []
        for nplot,plotopts in enumerate(contrib['content']['plots'].itervalues()):
            filename = '{}_{}_{}'.format(
                ('viewer' if isinstance(self.db, dict) else 'mp'), cid, nplot)
            table_name = plotopts.pop('table')
            plot_title = ' - '.join([contrib['mp_cat_id'], table_name])
            data = contrib['content']['_'.join([mp_level01_titles[1], table_name])]
            df = pandas.DataFrame.from_dict(data)
            # TODO: set xTitle and yTitle according to column header
            if isinstance(self.db, dict):
                # use Plotly Javascript Library -> list of x/y dicts
                xaxis, yaxis = plotopts['x'], plotopts.get('y', None)
                yaxes = [yaxis] if yaxis is not None else \
                        [col for col in df.columns if col != xaxis]
                xvals = df[xaxis].tolist()
                urls.append([[
                    {'x': xvals, 'y': df[axis].tolist(), 'name': axis}
                    for axis in yaxes
                ], {
                    'title': plot_title, 'xaxis': {'title': xaxis},
                    'yaxis': {
                        'title': plotopts.get('yaxis.title'),
                        'type': plotopts.get('yaxis.type')
                    }, 'legend': {'x': 0.7, 'y': 1}, 'margin': {'r': 0, 't': 40},
                }])
            else:
                # use Plotly Cloud
                urls.append(df.iplot(filename=filename, asUrl=True, **plotopts))
            #if len(urls) == len(contrib['content']['plots']): # TODO update
            #    pyfig = py.get_figure(urls[nplot])
            #    for ti,line in enumerate(ax.get_lines()):
            #        pyfig['data'][ti]['x'] = list(line.get_xdata())
            #        pyfig['data'][ti]['y'] = list(line.get_ydata())
            #    py.plot(pyfig, filename=filename, auto_open=False)
        plotly_urls = RecursiveDict({subfld: urls})
        return None if len(url_list) else plotly_urls

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
        mp_cat_id = contrib['mp_cat_id']
        is_mp_id = mp_id_pattern.match(mp_cat_id)
        self.curr_coll = self.materials if is_mp_id else self.compositions
        if contributor_email not in contrib['collaborators']: raise ValueError(
            "Build stopped: building contribution {} not "
            "allowed due to insufficient permissions of {}! Ask "
            "someone of {} to make you a collaborator on {}.".format(
                cid_short, contributor_email, contrib['collaborators'], cid_short))
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.') \
                if 'project' not in contrib else contrib['project']
        # prepare tree and table data
        all_data = RecursiveDict()
        for key,value in contrib['content'].iteritems():
            if key == 'cid' or key == 'plots' or key.startswith(mp_level01_titles[1]): continue
            all_data.rec_update(nest_dict(
                value, ['{}.{}.tree_data'.format(project, cid_str), key]
            ))
        for table_name, raw_data in contrib['content'].iteritems():
            if not table_name.startswith(mp_level01_titles[1]): continue
            table_columns, table_rows = None, None
            if isinstance(raw_data, dict):
                #table_columns = [ { 'title': k } for k in raw_data ]
                #table_rows = [
                #    [ str(raw_data[d['title']][row_index]) for d in table_columns ]
                #    for row_index in xrange(len(
                #        raw_data[table_columns[0]['title']]
                #    ))
                #]
                table_columns = [ { 'name': k, 'cell': 'string' } for k in raw_data ]
                table_rows = [
                    dict(
                        (d['name'], str(raw_data[d['name']][row_index]))
                        for d in table_columns
                    ) for row_index in xrange(len(
                        raw_data[table_columns[0]['name']]
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
                    '{}.{}.tables.{}.columns'.format(project, cid_str, table_name): table_columns,
                    '{}.{}.tables.{}.rows'.format(project, cid_str, table_name): table_rows,
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
            return [
              mp_cat_id, project, cid_str,
              self.curr_coll[mp_cat_id][project][cid_str]
            ]
        else:
            return '{}/{}/contributions#{}#{}'.format( # return URL for contribution page
                ('materials' if is_mp_id else 'compositions'),
                mp_cat_id, project, cid_short)
