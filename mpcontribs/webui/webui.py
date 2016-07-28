from __future__ import unicode_literals, print_function, absolute_import

import json, os, socket, SocketServer, codecs, time, pkgutil
import sys, warnings, multiprocessing
from IPython.terminal.ipapp import launch_new_instance
from flask import Flask, render_template, request, Response
from flask import url_for, redirect, make_response, stream_with_context
from celery import Celery
from mpcontribs.utils import process_mpfile, submit_mpfile
from mpcontribs.config import default_mpfile_path
from mpcontribs import users as mpcontribs_users
from StringIO import StringIO
from webtzite import configure_settings

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask('mpcontribs.webui', template_folder=tmpl_dir, static_folder=stat_dir)
app.config['JSON_SORT_KEYS'] = False
app.config['CELERY_BROKER_URL'] = 'django://'
app.secret_key = 'xxxrrr'

session = {}
mod_iter = pkgutil.iter_modules(mpcontribs_users.__path__)
projects = [ mod for imp, mod, ispkg in mod_iter if ispkg ]

import django
django.setup()
celery = Celery(
    app.name, broker=app.config['CELERY_BROKER_URL'],
    include=['webtzite.configure_settings']
)
celery.conf.update(app.config)
celery.conf.update(
    CELERY_TASK_RESULT_EXPIRES=3600,
    CELERY_ACCEPT_CONTENT=['pickle', 'json', 'msgpack', 'yaml'],
)

@celery.task(ignore_result=True)
def add(x, y):
    return x + y

def patched_finish(self):
    try:
        if not self.wfile.closed:
            self.wfile.flush()
            self.wfile.close()
    except socket.error:
        pass
    self.rfile.close()

SocketServer.StreamRequestHandler.finish = patched_finish

processes = {'NotebookProcess': None}

class NotebookProcess(multiprocessing.Process):
    def __init__(self):
        super(NotebookProcess, self).__init__(name='NotebookProcess')

    def run(self):
        sys.argv[1:] = []
        warnings.filterwarnings("ignore", module = "zmq.*")
        sys.argv.append("notebook")
        sys.argv.append("--IPKernelApp.pylab='inline'")
        sys.argv.append("--NotebookApp.ip=localhost")
        sys.argv.append("--NotebookApp.open_browser=False")
        sys.argv.append('--NotebookApp.allow_origin="*"')
        launch_new_instance()

def start_processes():
    global processes
    for process_name in processes.keys():
        if not processes[process_name]:
            processes[process_name] = globals()[process_name]()
            processes[process_name].start()

def stop_processes():
    global processes
    for process_name in processes.keys():
        if processes[process_name]:
            processes[process_name].terminate()
            processes[process_name] = None
            time.sleep(1)

def stream_template(template_name, **context):
    # http://stackoverflow.com/questions/13386681/streaming-data-with-python-and-flask
    # http://flask.pocoo.org/docs/patterns/streaming/#streaming-from-templates
    app.update_template_context(context)
    t = app.jinja_env.get_template(template_name)
    rv = t.stream(context)
    return rv

def reset_session():
    global session
    session.clear()
    session['projects'] = projects
    session['options'] = ["archieml"]
    session['contribute'] = {}
    sbx_content = app.config.get('SANDBOX_CONTENT')
    if sbx_content is not None:
        session['sbx_content'] = sbx_content
    stop_processes()
    start_processes()
    for suffix in ['_in.txt', '_out.txt']:
      filepath = default_mpfile_path.replace('.txt', suffix)
      if os.path.exists(filepath):
        os.remove(filepath)

def read_mpfile_to_view():
    output_mpfile_path = default_mpfile_path.replace('.txt', '_out.txt')
    if os.path.exists(output_mpfile_path):
        return codecs.open(output_mpfile_path, encoding='utf-8').read()
    else:
        return session.get('mpfile')

@app.route('/view')
def view():
    mpfile = read_mpfile_to_view()
    if mpfile is None:
        return render_template(
            'home.html', alert='Choose an MPFile!', session=session
        )
    fmt = session['options'][0]
    try:
        return Response(stream_with_context(stream_template(
            'index.html', session=session,
            content=process_mpfile(StringIO(mpfile), fmt=fmt)
        )))
    except:
        pass

@app.route('/')
def home():
    #print(add.delay(4, 4))
    reset_session()
    return render_template('home.html', session=session)

@app.route('/load')
def load():
    mpfile = session.get('mpfile')
    if mpfile is None:
        return render_template(
            'home.html', alert='Choose an MPFile!', session=session
        )
    input_mpfile_path = default_mpfile_path.replace('.txt', '_in.txt')
    with codecs.open(input_mpfile_path, encoding='utf-8', mode='w') as f:
        f.write(mpfile)
    return render_template('home.html', session=session)

@app.route('/contribute', methods=['GET', 'POST'])
def contribute():
    if request.method == 'GET':
        return render_template('contribute.html', session=session)
    elif request.method == 'POST':
        for k in request.form:
            v = session['contribute'].get(k)
            if not v or (request.form[k] and request.form[k] != v):
                session['contribute'][k] = request.form[k]
        for k,v in session['contribute'].iteritems():
            if not v:
                return render_template('contribute.html', session=session,
                                       missing='{} not set!'.format(k))
        mpfile = read_mpfile_to_view()
        if mpfile is None:
            return render_template(
                'home.html', alert='Choose an MPFile!', session=session
            )
        fmt = session['options'][0]
        try:
            return Response(stream_with_context(stream_template(
                'contribute.html', session=session, content=submit_mpfile(
                    StringIO(mpfile), api_key=session['contribute']['apikey'],
                    site=session['contribute']['site'],
                    dbtype=session['contribute']['dbtype'], fmt=fmt
                ))))
        except:
            pass

@app.route('/action', methods=['POST'])
def action():
    session['options'] = json.loads(request.form.get('options'))
    thebe_str = request.form.get('thebe')
    if thebe_str:
        session['thebe'] = '\n'.join(json.loads(thebe_str))
    fmt = session['options'][0]
    mpfile = request.files.get('file').read().decode('utf-8-sig')
    if not mpfile:
        mpfile = request.form.get('mpfile')
        if not mpfile:
            mpfile = session.get('mpfile')
            if not mpfile:
                return render_template(
                    'home.html', alert='Choose an MPFile!', session=session
                )
    session['mpfile'] = mpfile
    if request.form['submit'] == 'Load MPFile':
        return redirect(url_for('load'))
    elif request.form['submit'] == 'View MPFile':
        return redirect(url_for('view'))
    elif request.form['submit'] == 'Save MPFile':
        response = make_response(session['mpfile'])
        response.headers["Content-Disposition"] = "attachment; filename=mpfile.txt"
        return response
    elif request.form['submit'] == 'Contribute':
        return redirect(url_for('contribute'))

@app.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    stop_processes()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'
