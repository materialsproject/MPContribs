from __future__ import unicode_literals, print_function, absolute_import

import os
from flask import Blueprint, render_template, redirect

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
main_bp = Blueprint('webui_main', __name__, template_folder=tmpl_dir, static_folder=stat_dir)

@main_bp.route('/')
def home():
    from mpcontribs import MPContribsRester
    try:
        with MPContribsRester(test_site=True) as mpr:
            return render_template('main.html')
    except ValueError:
        jpy_user = os.environ.get('JPY_USER')
        if not jpy_user:
            raise ValueError('Cannot connect to test_site outside MP JupyterHub!')
        flaskproxy = 'https://jupyterhub.materialsproject.org/flaskproxy'
        login_url = '/'.join([flaskproxy, jpy_user, 'test_site/login'])
        return redirect(login_url)
