# -*- coding: utf-8 -*-
from django.conf.urls import url
from django.views.generic.base import RedirectView
from mpcontribs.portal import views

app_name = "mpcontribs_portal"
urlpatterns = [
    # public
    url(r"^$", views.index, name="index"),
    url(r"^work/?$", views.work, name="work"),
    url(r"^healthcheck/?$", views.healthcheck, name="healthcheck"),
    url(
        r"^notebooks/(?P<nb>[A-Za-z0-9_\/]{3,}).html$",
        views.notebooks,
        name="notebooks",
    ),
    url(
        r"^projects/(?P<project>[a-zA-Z0-9_]{3,}).json.gz$",
        views.download_project,
        name="download_project",
    ),
    # protected
    url(r"^browse/?$", views.browse, name="browse"),
    url(r"^search/?$", views.search, name="search"),
    url(r"^apply/?$", views.apply, name="apply"),
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
    # redirect
    url(
        r"^(?P<project>[a-zA-Z0-9_]{3,31})/?$",
        RedirectView.as_view(pattern_name="landingpage", permanent=False),
    ),
]
