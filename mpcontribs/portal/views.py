"""This module provides the views for the portal."""

from django.shortcuts import render_to_response

def index(request):
    return render_to_response("mpcontribs_portal_index.html")
