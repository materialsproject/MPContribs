from __future__ import unicode_literals, print_function
import json, os
from flask import Flask, render_template, request, url_for, redirect, session
from mpcontribs.utils import submit_mpfile, get_short_object_id
from six import string_types
from StringIO import StringIO
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('webui', template_folder=tmpl_dir, static_folder=stat_dir)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = 'xxxrrr'

@app.route('/default', methods=['GET', 'POST'])
@app.route('/graphs', methods=['GET', 'POST'])
def index():
    mpfile = request.args.get('mpfile')
    if mpfile is None:
        mpfile = StringIO(session.get('mpfile'))
        if mpfile is None:
            return render_template('home.html')
    content = submit_mpfile(mpfile, test=True)
    for value in content.itervalues():
        for project_data in value.itervalues():
            for cid in project_data:
                cid_short = get_short_object_id(cid)
                d = project_data.pop(cid)
                project_data[cid_short] = d
    template = 'graphs.html' if 'graphs' in request.path else 'index.html'
    return render_template(template, content=content)

@app.route('/')
@app.route('/load', methods=['GET', 'POST'])
def home():
    mpfile = request.args.get('mpfile')
    if mpfile is None:
        mpfile = session.get('mpfile') if request.path != '/' else None
        if mpfile is None:
            return render_template('home.html')
    else:
        mpfile = open(mpfile, 'r').read()
    return render_template('home.html', content={'aml': mpfile.decode('utf-8-sig')})

@app.route('/action', methods=['POST'])
def action():
    session['mpfile'] = request.files.get('file').read()
    if request.form['submit'] == 'Load MPFile':
        return redirect('/load')
    elif request.form['submit'] == 'View MPFile':
        return redirect('/default')
    elif request.form['submit'] == 'View Graphs':
        return redirect('/graphs')
    else:
        return redirect('/')

@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'
