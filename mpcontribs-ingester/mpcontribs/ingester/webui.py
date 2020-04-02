from __future__ import unicode_literals, print_function, absolute_import

import json, os, socket, codecs, time, psutil
import sys, warnings, multiprocessing
from tempfile import gettempdir
from flask import render_template, request, Response, Blueprint, current_app
from flask import url_for, redirect, make_response, stream_with_context, jsonify
from mpcontribs.utils import process_mpfile, submit_mpfile
from mpcontribs.users_modules import *
from whichcraft import which
from subprocess import call

default_mpfile_path = os.path.join(gettempdir(), 'mpfile.txt')

try:
    import SocketServer as socketserver
except ImportError:
    import socketserver

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
ingester_bp = Blueprint('webui_ingester', __name__, template_folder=tmpl_dir, static_folder=stat_dir)

session = {}
projects = {}
for mod_path in get_users_modules():
    mod = os.path.basename(mod_path)
    path = os.path.join(mod_path, 'mpfile_init.txt')
    if os.path.exists(path):
        projects[mod] = codecs.open(path, encoding='utf-8').read()
    else:
        projects[mod] = ''

def patched_finish(self):
    try:
        if not self.wfile.closed:
            self.wfile.flush()
            self.wfile.close()
    except socket.error:
        pass
    self.rfile.close()

socketserver.StreamRequestHandler.finish = patched_finish

processes = {'NotebookProcess': None, 'MongodProcess': None}

class NotebookProcess(multiprocessing.Process):
    def __init__(self):
        super(NotebookProcess, self).__init__(name='NotebookProcess')

    def run(self):
        from IPython.terminal.ipapp import launch_new_instance
        sys.argv[1:] = []
        warnings.filterwarnings("ignore", module = "zmq.*")
        sys.argv.append("notebook")
        sys.argv.append("--IPKernelApp.pylab='inline'")
        sys.argv.append("--NotebookApp.ip=0.0.0.0")
        sys.argv.append("--NotebookApp.open_browser=False")
        sys.argv.append('--NotebookApp.allow_origin="*"')
        #sys.argv.append('--NotebookApp.port_retries=0')
        launch_new_instance()

class MongodProcess(multiprocessing.Process):
    def __init__(self):
        super(MongodProcess, self).__init__(name='MongodProcess')

    def run(self):
        if which('mongod'):
            cwd = os.path.join(os.path.dirname(__file__), '..', '..')
            dbpath = os.path.join('/', 'data', 'db')
            if not os.path.exists(dbpath):
                dbpath = os.path.join(cwd, 'db')
            logpath = os.path.join(dbpath, 'mongodb-mpcontribs.log')
            call(['mongod', '--dbpath', dbpath, '--logpath', logpath, '--logappend'])
            print('mongod started.')
        else:
            print('install MongoDB to use local DB instance.')

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
            if process_name != 'MongodProcess':
                processes[process_name].terminate()
                time.sleep(1)
            processes[process_name] = None
    parent = psutil.Process(os.getpid())
    for child in parent.children(recursive=True):
        if child.name() == 'mongod':
            child.kill()
            print('killed mongod')

def stream_template(template_name, **context):
    # http://stackoverflow.com/questions/13386681/streaming-data-with-python-and-flask
    # http://flask.pocoo.org/docs/patterns/streaming/#streaming-from-templates
    current_app.update_template_context(context)
    t = current_app.jinja_env.get_template(template_name)
    rv = t.stream(context)
    return rv

def reset_session():
    global session, processes
    current_app.config['JSON_SORT_KEYS'] = False
    current_app.secret_key = 'xxxrrr'
    session.clear()
    session['projects'] = projects
    session['options'] = ["archieml"]
    session['contribute'] = {}
    sbx_content = current_app.config.get('SANDBOX_CONTENT')
    if sbx_content is not None:
        session['sbx_content'] = sbx_content
    session['jupyter_url'] = current_app.config.get('JUPYTER_URL')
    if not current_app.config.get('START_JUPYTER') and 'NotebookProcess' in processes:
        processes.pop('NotebookProcess')
    if not current_app.config.get('START_MONGODB') and 'MongodProcess' in processes:
        processes.pop('MongodProcess')
    stop_processes()
    start_processes()
    for suffix in ['_in.txt', '_out.txt']:
      filepath = default_mpfile_path.replace('.txt', suffix)
      if os.path.exists(filepath):
        os.remove(filepath)

def read_mpfile_to_view():
    output_mpfile_path = default_mpfile_path.replace('.txt', '_out.txt')
    if os.path.exists(output_mpfile_path):
        return open(output_mpfile_path).read()
    else:
        return session.get('mpfile')

@ingester_bp.route('/view')
@ingester_bp.route('/view/<identifier>/<cid_short>')
def view(identifier=None, cid_short=None):
    mpfile = read_mpfile_to_view()
    if mpfile is None:
        return render_template(
            'home.html', alert='Choose an MPFile!', session=session
        )
    fmt = session['options'][0]
    try:
        mpfile_stringio = StringIO(mpfile)
        if identifier is None or cid_short is None:
            response = Response(stream_with_context(stream_template(
                'index.html', session=session,
                content=process_mpfile(mpfile_stringio, fmt=fmt)
            )))
            response.headers['X-Accel-Buffering'] = 'no'
            return response
        else:
            ids = [identifier, cid_short]
            iterator = process_mpfile(mpfile_stringio, fmt=fmt, ids=ids)
            for it in iterator:
                if isinstance(it, list):
                    d = jsonify(it)
            return d
    except Exception:
        pass

@ingester_bp.route('/')
def home():
    reset_session()
    return render_template('home.html', session=session)

@ingester_bp.route('/load')
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

@ingester_bp.route('/contribute', methods=['GET', 'POST'])
def contribute():
    session['scheme'] = 'https' if os.environ.get('DEPLOYMENT') == 'MATGEN' else 'http'
    if request.method == 'GET':
        return render_template('contribute.html', session=session)
    elif request.method == 'POST':
        for k in request.form:
            v = session['contribute'].get(k)
            if not v or (request.form[k] and request.form[k] != v):
                session['contribute'][k] = request.form[k]
        if not session['contribute'].get('site'):
            return render_template('contribute.html', session=session,
                                   missing='site not set!')
        mpfile = read_mpfile_to_view()
        if mpfile is None:
            return render_template(
                'home.html', alert='Choose an MPFile!', session=session
            )
        fmt = session['options'][0]
        try:
            response = Response(stream_with_context(stream_template(
                'contribute.html', session=session, content=submit_mpfile(
                    StringIO(mpfile), site=session['contribute']['site'],
                    fmt=fmt, project=session['options'][1]
                ))))
            response.headers['X-Accel-Buffering'] = 'no'
            return response
        except Exception:
            pass

@ingester_bp.route('/action', methods=['POST'])
def action():
    session['options'] = json.loads(request.form.get('options'))
    thebe_str = request.form.get('thebe')
    if thebe_str:
        session['thebe'] = '\n'.join(json.loads(thebe_str))
    #fmt = session['options'][0]
    mpfile = request.files.get('file', StringIO()).read().decode('utf-8-sig')
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
        return redirect(url_for('.load'))
    elif request.form['submit'] == 'View MPFile':
        return redirect(url_for('.view'))
    elif request.form['submit'] == 'Save MPFile':
        response = make_response(read_mpfile_to_view())
        response.headers["Content-Disposition"] = "attachment; filename=mpfile.txt"
        return response
    elif request.form['submit'] == 'Contribute':
        return redirect(url_for('.contribute'))

@ingester_bp.route('/shutdown', methods=['GET', 'POST'])
def shutdown():
    stop_processes()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'
