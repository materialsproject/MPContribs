# http://flask.pocoo.org/docs/0.10/patterns/appdispatch/
import os, argparse
from werkzeug.serving import run_simple
from werkzeug.wsgi import DispatcherMiddleware, SharedDataMiddleware
from flask import Flask
from mpcontribs.webui.main import main_bp
from mpcontribs.webui.webui import ingester_bp
from test_site.wsgi import application as django_app
from test_site.settings import STATIC_ROOT_URLS, PROXY_URL_PREFIX

def cli():
    parser = argparse.ArgumentParser(
        description='Command Line Interface for MPContribs WebUI',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--sbx', help='ArchieML Sandbox Content')
    parser.add_argument('--debug', action='store_true', help='run in debug mode')
    parser.add_argument('--start-jupyter', action='store_true', help='start Jupyter server')
    parser.add_argument('--start-mongodb', action='store_true', help='start MongoDB server')
    jpy_base_url = os.environ.get('JPY_BASE_URL')
    if os.environ.get('DEPLOYMENT') == 'MATGEN':
        default_jupyter_url = 'https://jupyterhub.materialsproject.org' + jpy_base_url
    else:
        default_jupyter_url = 'http://localhost:'
        default_jupyter_url += '8000'+jpy_base_url if jpy_base_url else '8888'
    parser.add_argument('--jupyter-url', metavar='URL', dest='jupyter_url',
                        default=default_jupyter_url, help='Jupyter URL')
    args = parser.parse_args()

    if args.start_mongodb:
        dbpath = os.path.join('/', 'data', 'db')
        if not os.path.exists(dbpath):
            dbpath = os.path.join(cwd, 'db')
            if not os.path.exists(dbpath):
                os.makedirs(dbpath)

    app = Flask(__name__)
    app.debug = args.debug
    app.config['SANDBOX_CONTENT'] = args.sbx
    app.config['START_JUPYTER'] = args.start_jupyter
    app.config['START_MONGODB'] = args.start_mongodb
    app.config['JUPYTER_URL'] = args.jupyter_url
    app.register_blueprint(main_bp, url_prefix=PROXY_URL_PREFIX)
    app.register_blueprint(ingester_bp, url_prefix=PROXY_URL_PREFIX + '/ingester')

    application = DispatcherMiddleware(app, {PROXY_URL_PREFIX + '/test_site': django_app})
    application = SharedDataMiddleware(application, STATIC_ROOT_URLS)

    run_simple('0.0.0.0', 5000, application, use_reloader=args.debug,
               use_debugger=args.debug, use_evalex=args.debug, threaded=True)

if __name__ == '__main__':
    cli()
