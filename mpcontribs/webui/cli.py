# http://flask.pocoo.org/docs/0.10/patterns/appdispatch/
import os, argparse
from werkzeug.serving import run_simple
from werkzeug.wsgi import DispatcherMiddleware, SharedDataMiddleware
from mpcontribs.webui.webui import app as flask_app
from test_site.wsgi import application as django_app
from test_site.settings import STATIC_ROOT
from django.core.management import call_command
from subprocess import call

def cli():
    parser = argparse.ArgumentParser(
        description='Command Line Interface for MPContribs WebUI',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--sbx', help='ArchieML Sandbox Content')
    parser.add_argument('--debug', action='store_true', help='run in debug mode')
    args = parser.parse_args()

    cwd = os.path.join(os.path.dirname(__file__), '..', '..')
    os.chdir(os.path.join(cwd, 'mpcontribs', 'rest'))
    call(['./apidoc.sh'])
    os.chdir(cwd)

    dbpath = os.path.join(cwd, 'db')
    if not os.path.exists(dbpath):
        os.makedirs(dbpath)

    flask_app.debug = args.debug
    flask_app.config['SANDBOX_CONTENT'] = args.sbx
    call_command('collectstatic', '--clear', '--noinput', '-v 0')
    print 'static files collected.'

    application = DispatcherMiddleware(flask_app, { '/test_site': django_app })
    application = SharedDataMiddleware(application, { '/static': STATIC_ROOT })

    run_simple('0.0.0.0', 5000, application, use_reloader=args.debug,
               use_debugger=args.debug, use_evalex=args.debug, threaded=True)

if __name__ == '__main__':
    cli()
