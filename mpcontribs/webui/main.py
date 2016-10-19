from __future__ import unicode_literals, print_function, absolute_import

import os
from flask import Blueprint, render_template

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
stat_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
main_bp = Blueprint('webui_main', __name__, template_folder=tmpl_dir, static_folder=stat_dir)

@main_bp.route('/')
def home():
    return render_template('main.html')
