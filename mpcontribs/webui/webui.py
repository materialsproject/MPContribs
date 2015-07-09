import json, os, pwd
from flask import Flask, render_template
from mpcontribs.io.mpfile import MPFile
from mpcontribs.rest import ContributionMongoAdapter
from mpcontribs.builders import MPContributionsBuilder
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('webui', template_folder=tmpl_dir, static_folder=stat_dir)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    if not path: return 'Append path to URL in order to view MPFile'
    full_name = pwd.getpwuid(os.getuid())[4]
    contributor = '{} <phuck@lbl.gov>'.format(full_name)
    mpfile = MPFile.from_file(path)
    cma = ContributionMongoAdapter()
    docs = cma.submit_contribution(mpfile, contributor)
    mcb = MPContributionsBuilder(docs)
    mcb.build(contributor)
    return render_template('index.html', content=mcb.mat_coll)
