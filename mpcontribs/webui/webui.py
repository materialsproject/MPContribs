from __future__ import unicode_literals, print_function
import json, os
from flask import Flask, render_template, request
from flask import url_for, redirect, make_response
from mpcontribs.utils import submit_mpfile, get_short_object_id
from six import string_types
from StringIO import StringIO
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('webui', template_folder=tmpl_dir, static_folder=stat_dir)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = 'xxxrrr'

session = {}

@app.route('/view/<template>')
def view(template):
    if template not in ['graphs', 'index']:
        return render_template(
            'home.html', alert='view endpoint {} not accepted!'.format(template)
        )
    mpfile, fmt = session.get('mpfile'), session.get('fmt')
    if mpfile is None:
        return render_template('home.html', alert='Choose an MPFile!', fmt=fmt)
    content = submit_mpfile(StringIO(mpfile), fmt=fmt)
    for value in content.itervalues():
        for project_data in value.itervalues():
            for cid in project_data:
                cid_short = get_short_object_id(cid)
                d = project_data.pop(cid)
                project_data[cid_short] = d
    return render_template('{}.html'.format(template), content=content, fmt=fmt)

@app.route('/')
def home():
    session.clear()
    return render_template('home.html')

@app.route('/load')
def load():
    mpfile, fmt = session.get('mpfile'), session.get('fmt')
    if mpfile is None:
        return render_template('home.html', alert='Choose an MPFile!', fmt=fmt)
    return render_template('home.html', content={'aml': mpfile}, fmt=fmt)

@app.route('/action', methods=['POST'])
def action():
    fmt = request.form.get('fmt')
    mpfile = request.files.get('file').read().decode('utf-8-sig')
    if not mpfile:
        mpfile = request.form.get('mpfile')
        if not mpfile:
            mpfile = session.get('mpfile')
            if not mpfile:
                return render_template('home.html', alert='Choose an MPFile!', fmt=fmt)
    session['mpfile'] = mpfile
    session['fmt'] = fmt
    if request.form['submit'] == 'Load MPFile':
        return redirect(url_for('load'))
    elif request.form['submit'] == 'View MPFile':
        return redirect(url_for('view', template='index'))
    elif request.form['submit'] == 'View Graphs':
        return redirect(url_for('view', template='graphs'))
    elif request.form['submit'] == 'Save MPFile':
        response = make_response(session['mpfile'])
        response.headers["Content-Disposition"] = "attachment; filename=mpfile.txt"
        return response

@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'
