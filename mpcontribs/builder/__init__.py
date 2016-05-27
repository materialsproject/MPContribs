import os, re, bson, pandas, nbformat
from itertools import groupby
from mpcontribs.io.core.recdict import RecursiveDict
from mpcontribs.io.core.utils import get_short_object_id, nest_dict
from mpcontribs.config import mp_level01_titles, mp_id_pattern
from mpcontribs.pmg_utils.author import Author
from mpcontribs.io.core.mpfile import MPFileCore
from nbformat import v4 as nbf
from nbconvert.preprocessors import ExecutePreprocessor
from nbconvert.preprocessors.execute import CellExecutionError

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
        return self.db if isinstance(self.db, dict) else \
                self.contributions.find_one({'_id': cid})

    def build(self, contributor_email, cid):
        """update materials/compositions collections with contributed data"""
        cid_short, cid_str = get_short_object_id(cid), str(cid)
        contrib = self.find_contribution(cid)
        if contributor_email not in contrib['collaborators']: raise ValueError(
            "Build stopped: building contribution {} not "
            "allowed due to insufficient permissions of {}! Ask "
            "someone of {} to make you a collaborator on {}.".format(
                cid_short, contributor_email, contrib['collaborators'], cid_short))
        mpfile = MPFileCore.from_contribution(contrib)
        mp_cat_id = mpfile.ids[0]
        is_mp_id = mp_id_pattern.match(mp_cat_id)
        self.curr_coll = self.materials if is_mp_id else self.compositions
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.') \
                if 'project' not in contrib else contrib['project']

        nb = nbf.new_notebook()
        nb['cells'].append(nbf.new_code_cell(
            "from mpcontribs.rest.rester import MPContribsRester"
        ))
        # NOTE need to get API_KEY from user when executing NB on server
        nb['cells'].append(nbf.new_code_cell(
            "with MPContribsRester() as mpr:\n"
            "    mpfile = mpr.find_contribution('{}')\n"
            "    mpid = mpfile.ids[0]"
            .format(cid)
        ))
        nb['cells'].append(nbf.new_markdown_cell(
            "# Contribution #{} for {}\n"
            "## Hierarchical Data"
            .format(cid_short, mp_cat_id)
        ))
        nb['cells'].append(nbf.new_code_cell(
            "hdata = mpfile.hdata[mpid]\n"
            "hdata"
        ))
        nb['cells'].append(nbf.new_markdown_cell("## Tabular Data"))
        for table_name, table in mpfile.tdata[mp_cat_id].iteritems():
            nb['cells'].append(nbf.new_markdown_cell(
                "### {}".format(table_name)
            ))
            nb['cells'].append(nbf.new_code_cell(
                "{} = mpfile.tdata[mpid]['{}'] # pandas.DataFrame\n"
                "{}".format(table_name, table_name, table_name)
            ))
        nb['cells'].append(nbf.new_markdown_cell("## Graphical Data"))
        for plot_name, plot in mpfile.gdata[mp_cat_id].iteritems():
            nb['cells'].append(nbf.new_markdown_cell(
                "### {}".format(plot_name)
            ))
            nb['cells'].append(nbf.new_code_cell(
                "{} = mpfile.gdata[mpid]['{}']\n"
                "{}".format(plot_name, plot_name, plot_name)
            ))

        nbdir = os.path.dirname(os.path.abspath(__file__))
        ep = ExecutePreprocessor(timeout=600, kernel_name='python2')
        try:
            out = ep.preprocess(nb, {'metadata': {'path': nbdir}})
        except CellExecutionError:
            print 'Execution error in above cell!' # TODO logging
        finally:
            nbpath = os.path.join(nbdir, 'test.ipynb')
            with open(nbpath, mode='wt') as f:
                nbformat.write(nb, f)

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
