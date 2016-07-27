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
    args = parser.parse_args()

    cwd = os.getcwd()
    os.chdir(os.path.join('mpcontribs', 'rest'))
    call(['./apidoc.sh'])
    os.chdir(cwd)

    flask_app.debug = True
    flask_app.config['SANDBOX_CONTENT'] = args.sbx
    call_command('collectstatic', '--clear', '--noinput', '-v 0')
    print 'static files collected.'

    application = DispatcherMiddleware(flask_app, { '/test_site': django_app })
    application = SharedDataMiddleware(application, { '/static': STATIC_ROOT })

    run_simple('localhost', 5000, application, use_reloader=True,
               use_debugger=True, use_evalex=True, threaded=True)

if __name__ == '__main__':
    cli()
