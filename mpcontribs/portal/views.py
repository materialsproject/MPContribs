"""This module provides the views for the portal."""

from django.shortcuts import render_to_response
from mpcontribs.utils import get_user_explorer_name, get_user_modules
import os

def index(request):
    a_tags = []
    for mod_path in get_user_modules():
        explorer = os.path.join(mod_path, 'explorer', 'urls.py')
        if os.path.exists(explorer):
            a_tags.append({
                'name': get_user_explorer_name(explorer),
                'title': os.path.basename(mod_path).replace('_', ' ')
            })
    return render_to_response("mpcontribs_portal_index.html", locals())
