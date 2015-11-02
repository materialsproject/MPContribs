from __future__ import unicode_literals, print_function, absolute_import

import json, os, socket, SocketServer
import sys, warnings, multiprocessing
from IPython.terminal.ipapp import launch_new_instance
from flask import Flask, render_template, request, Response
from flask import url_for, redirect, make_response, stream_with_context
from mpcontribs.utils import process_mpfile, submit_mpfile
from StringIO import StringIO
tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('mpcontribs.webui', template_folder=tmpl_dir, static_folder=stat_dir)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = 'xxxrrr'

session = {}

def patched_finish(self):
    try:
        if not self.wfile.closed:
            self.wfile.flush()
            self.wfile.close()
    except socket.error:
        pass
    self.rfile.close()

SocketServer.StreamRequestHandler.finish = patched_finish

class NotebookProcess(multiprocessing.Process):
    def __init__(self):
        super(NotebookProcess, self).__init__(name='notebook_process')

    def run(self):
        warnings.filterwarnings("ignore", module = "zmq.*")
        sys.argv.append("notebook")
        sys.argv.append("--IPKernelApp.pylab='inline'")
        sys.argv.append("--NotebookApp.ip=localhost")
        sys.argv.append("--NotebookApp.open_browser=False")
        sys.argv.append('--NotebookApp.allow_origin="*"')
        launch_new_instance()

def start_notebook():
    global notebook_process
    if not notebook_process:
        notebook_process = NotebookProcess()
        notebook_process.start()

def stop_notebook():
    global notebook_process
    if notebook_process:
        notebook_process.terminate()
        notebook_process = None

def stream_template(template_name, **context):
    # http://stackoverflow.com/questions/13386681/streaming-data-with-python-and-flask
    # http://flask.pocoo.org/docs/patterns/streaming/#streaming-from-templates
    app.update_template_context(context)
    t = app.jinja_env.get_template(template_name)
    rv = t.stream(context)
    return rv

notebook_process = None

@app.route('/view/<template>')
def view(template):
    mpfile, fmt = session.get('mpfile'), session.get('fmt')
    if template not in ['graphs', 'index']:
        return render_template(
            'home.html', fmt=fmt,
            alert='view endpoint {} not accepted!'.format(template)
        )
    if mpfile is None:
        return render_template('home.html', alert='Choose an MPFile!', fmt=fmt)
    return Response(stream_with_context(stream_template(
        '{}.html'.format(template), fmt=fmt,
        content=process_mpfile(StringIO(mpfile), fmt=fmt)
    )))

@app.route('/')
def home():
    session.clear()
    stop_notebook()
    start_notebook()
    return render_template('home.html', fmt='archieml')

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
    elif request.form['submit'] == 'Contribute':
        try:
            return Response(stream_with_context(stream_template(
                'contribute.html', fmt=fmt,
                content=submit_mpfile(StringIO(mpfile), fmt=fmt)
            )))
        except:
            pass

@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    stop_notebook()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'
