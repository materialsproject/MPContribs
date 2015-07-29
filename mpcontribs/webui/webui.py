from __future__ import unicode_literals, print_function
import json, os
from flask import Flask, render_template, request
from mpcontribs.utils import submit_mpfile, get_short_object_id
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('webui', template_folder=tmpl_dir, static_folder=stat_dir)
app.config['JSON_SORT_KEYS'] = False

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
@app.route('/graphs/<path:path>', methods=['GET', 'POST'])
def index(path):
    if not path and request.method == 'GET':
        return render_template('choose.html')
    mpfile = path if path else request.files['file']
    content = submit_mpfile(mpfile, test=True)
    for value in content.itervalues():
        for project_data in value.itervalues():
            for cid in project_data:
                cid_short = get_short_object_id(cid)
                d = project_data.pop(cid)
                project_data[cid_short] = d
    template = 'graphs.html' if 'graphs' in request.path else 'index.html'
    return render_template(template, content=content)
