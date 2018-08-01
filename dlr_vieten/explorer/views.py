"""This module provides the views for the dlr_vieten explorer interface."""

import os
from django.shortcuts import render_to_response
from django.template import RequestContext
from mpcontribs.rest.views import get_endpoint
from mpcontribs.io.core.components import render_dataframe
from mpcontribs.io.core.recdict import render_dict
from test_site.settings import STATIC_URL, DEBUG
from webtzite.models import RegisteredUser

access_msg = 'Coming Soon! Contact <a href="mailto:josua.vieten@dlr.de">J. Vieten</a> to request pre-publication access.'

def index(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        if user.groups.filter(name='dlr_vieten').exists():
            API_KEY = user.api_key
            ENDPOINT = request.build_absolute_uri(get_endpoint())
            from ..rest.rester import DlrVietenRester
            with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
                try:
                    ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                    prov = mpr.get_provenance()
                    ctx['title'] = prov.pop('title')
                    ctx['provenance'] = render_dict(prov, webapp=True)
                    ctx['static_url'] = STATIC_URL
                    if DEBUG:
                        mod = os.path.dirname(__file__).split(os.sep)[-2]
                        ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod])
                except Exception as ex:
                    ctx.update({'alert': str(ex)})
        else:
            ctx.update({'alert': access_msg})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_index.html", ctx)

def isographs(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        if user.groups.filter(name='dlr_vieten').exists():
            API_KEY = user.api_key
            ENDPOINT = request.build_absolute_uri(get_endpoint())
            from ..rest.rester import DlrVietenRester
            with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
                try:
                    ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                    prov = mpr.get_provenance()
                    ctx['title'] = prov.pop('title')
                    ctx['provenance'] = render_dict(prov, webapp=True)
                except Exception as ex:
                    ctx.update({'alert': str(ex)})
        else:
            ctx.update({'alert': access_msg})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_isographs.html", ctx)

def energy_analysis(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        if user.groups.filter(name='dlr_vieten').exists():
            API_KEY = user.api_key
            ENDPOINT = request.build_absolute_uri(get_endpoint())
            from ..rest.rester import DlrVietenRester
            with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
                try:
                    ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                    prov = mpr.get_provenance()
                    ctx['title'] = prov.pop('title')
                    ctx['provenance'] = render_dict(prov, webapp=True)
                    ctx['static_url'] = STATIC_URL
                    if DEBUG:
                        mod = os.path.dirname(__file__).split(os.sep)[-2]
                        ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod])
                except Exception as ex:
                    ctx.update({'alert': str(ex)})
        else:
            ctx.update({'alert': access_msg})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_energy_analysis.html", ctx)

def documentation(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        if user.groups.filter(name='dlr_vieten').exists():
            API_KEY = user.api_key
            ENDPOINT = request.build_absolute_uri(get_endpoint())
            from ..rest.rester import DlrVietenRester
            with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
                try:
                    ctx['table'] = render_dataframe(mpr.get_contributions(), webapp=True)
                    prov = mpr.get_provenance()
                    ctx['title'] = prov.pop('title')
                    ctx['provenance'] = render_dict(prov, webapp=True)
                    ctx['static_url'] = STATIC_URL
                    if DEBUG:
                        mod = os.path.dirname(__file__).split(os.sep)[-2]
                        ctx['static_url'] = '_'.join([STATIC_URL[:-1], mod])
                except Exception as ex:
                    ctx.update({'alert': str(ex)})
        else:
            ctx.update({'alert': access_msg})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_documentation.html", ctx)

def tolerance_factors(request):
    ctx = RequestContext(request)
    if request.user.is_authenticated():
        user = RegisteredUser.objects.get(username=request.user.username)
        API_KEY = user.api_key
        ENDPOINT = request.build_absolute_uri(get_endpoint())
        from ..rest.rester import DlrVietenRester
        with DlrVietenRester(API_KEY, endpoint=ENDPOINT) as mpr:
            try:
                ionic_radii = render_dataframe(mpr.get_ionic_radii(), webapp=True)
            except Exception as ex:
                ctx.update({'alert': str(ex)})
    else:
        ctx.update({'alert': 'Please log in!'})
    return render_to_response("dlr_vieten_explorer_tolerance_factors.html", ctx)
