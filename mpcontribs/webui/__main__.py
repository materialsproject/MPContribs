# http://flask.pocoo.org/docs/0.10/patterns/appdispatch/
from werkzeug.serving import run_simple
from werkzeug.wsgi import DispatcherMiddleware, SharedDataMiddleware
from mpcontribs.webui.webui import app as flask_app
from test_site.wsgi import application as django_app
from django.core.management import call_command

flask_app.debug = True
call_command('collectstatic', '--clear', '--noinput', '-v 0')

application = DispatcherMiddleware(flask_app, { '/test_site': django_app })
application = SharedDataMiddleware(application, { '/static': '/tmp/static' })

if __name__ == '__main__':
    run_simple('localhost', 5000, application, use_reloader=True,
               use_debugger=True, use_evalex=True, threaded=True)
