# -*- coding: utf-8 -*-
from django.conf.urls import url
from django.views.generic.base import RedirectView
from mpcontribs.portal import views

app_name = "mpcontribs_portal"
urlpatterns = [
    url(r"^$", views.index, name="index"),
    url(r"^public/?$", views.public, name="public"),
    url(r"^healthcheck/?$", views.healthcheck, name="healthcheck"),
    url(
        r"^notebooks/(?P<nb>[A-Za-z0-9_\/]{3,}).html$",
        views.notebooks,
        name="notebooks",
    ),
    url(r"^(?P<cid>[a-f\d]{24})/?$", views.contribution, name="contribution"),
    # downloads
    url(r"^download/?$", views.download, name="download"),
    url(
        r"^component/(?P<oid>[a-f\d]{24})$",
        views.download_component,
        name="download_component",
    ),
    url(
        r"^(?P<cid>[a-f\d]{24}).json.gz$",
        views.download_contribution,
        name="download_contribution",
    ),
    url(  # TODO extend to non-ML and csv
        r"^(?P<project>[a-zA-Z0-9_]{3,}).json.gz$",
        views.download_project,
        name="download_project",
    ),
    # redirects
    url(r"^fe-co-v/?$", RedirectView.as_view(url="/swf/", permanent=False)),
    url(r"^fe-co-v/dataset-01/?$", RedirectView.as_view(url="/swf/", permanent=False)),
    url(
        r"^boltztrap/?$",
        RedirectView.as_view(url="/carrier_transport/", permanent=True),
    ),
    url(
        r"^Screeninginorganicpv/?$",
        RedirectView.as_view(url="/screening_inorganic_pv/", permanent=False),
    ),
    url(
        r"^ScreeningInorganicPV/?$",
        RedirectView.as_view(url="/screening_inorganic_pv/", permanent=False),
    ),
    # default view
    url(r"^(?P<project>[a-zA-Z0-9_]{3,})/?$", views.landingpage, name="landingpage"),
]
