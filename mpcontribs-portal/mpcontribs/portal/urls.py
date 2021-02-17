# -*- coding: utf-8 -*-
from django.conf.urls import url
from django.views.generic.base import RedirectView
from mpcontribs.portal import views

app_name = "mpcontribs_portal"
urlpatterns = [
    # public
    #url(r"^$", views.index, name="index"),
    url(r"^$", RedirectView.as_view(pattern_name="browse")),
    url(r"^code/?$", views.work, name="work"),
    url(r"^work/?$", RedirectView.as_view(pattern_name="work")),
    url(r"^healthcheck/?$", views.healthcheck, name="healthcheck"),
    url(
        r"^notebooks/(?P<nb>[A-Za-z0-9_\/]{3,}).html$",
        views.notebooks,
        name="notebooks",
    ),
    url(
        r"^projects/(?P<project>[a-zA-Z0-9_]{3,31}).json.gz$",
        views.download_project,
        name="download_project",
    ),
    # protected
    url(r"^browse/?$", views.browse, name="browse"),
    url(r"^search/?$", views.search, name="search"),
    url(r"^contribute/?$", views.apply, name="apply"),
    url(r"^apply/?$", RedirectView.as_view(pattern_name="apply")),
    url(
        r"^projects/(?P<project>[a-zA-Z0-9_]{3,})/?$",
        views.landingpage,
        name="landingpage",
    ),
    url(r"^contributions/download/?$", views.download, name="download"),
    url(
        r"^contributions/component/(?P<oid>[a-f\d]{24})$",
        views.download_component,
        name="download_component",
    ),
    url(
        r"^contributions/(?P<cid>[a-f\d]{24}).json.gz$",
        views.download_contribution,
        name="download_contribution",
    ),
    url(
        r"^contributions/(?P<cid>[a-f\d]{24})/?$",
        views.contribution,
        name="contribution",
    ),
    # redirects
    url(r"^boltztrap/?$", RedirectView.as_view(url="/projects/carrier_transport")),
    url(r"^fe-co-v/?$", RedirectView.as_view(url="/projects/swf")),
    url(r"^Fe-Co-V/?$", RedirectView.as_view(url="/projects/swf")),
    url(
        r"^ScreeningInorganicPV/?$",
        RedirectView.as_view(url="/projects/screening_inorganic_pv")
    ),
    url(
        r"^(?P<project>[a-zA-Z0-9_]{3,31})/?$",
        RedirectView.as_view(pattern_name="landingpage", permanent=False),
    ),
]
