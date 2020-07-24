# -*- coding: utf-8 -*-
"""This module provides the views for the portal."""

import os
import gzip
import json
import nbformat
from glob import glob
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from bravado.exception import HTTPNotFound
from fido.exceptions import HTTPTimeoutError
from json2html import Json2Html
from boltons.iterutils import remap

from django.shortcuts import render, redirect
from django.template import RequestContext
from django.http import HttpResponse
from django.template.loaders.app_directories import get_app_template_dirs
from django.template.loader import select_template

from mpcontribs.client import Client

S3_DOWNLOADS_BUCKET = os.environ.get("S3_DOWNLOADS_BUCKET", "mpcontribs-downloads")
S3_DOWNLOAD_URL = f"https://{S3_DOWNLOADS_BUCKET}.s3.amazonaws.com/"
j2h = Json2Html()


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return key not in ["value", "unit"]


def get_consumer(request):
    names = ["X-Consumer-Groups", "X-Consumer-Username"]
    headers = {}
    for name in names:
        key = f'HTTP_{name.upper().replace("-", "_")}'
        value = request.META.get(key)
        if value is not None:
            headers[name] = value
    return headers


def get_context(request):
    ctx = RequestContext(request)
    ctx["API_CNAME"] = os.environ["API_CNAME"]
    ctx["API_PORT"] = os.environ["API_PORT"]
    ctx["TRADEMARK"] = os.environ.get("TRADEMARK", "")
    return ctx


def landingpage(request):
    ctx = get_context(request)
    try:
        project = request.path.replace("/", "")
        client = Client(headers=get_consumer(request))
        prov = client.projects.get_entry(pk=project, _fields=["_all"]).result()
        ctx["name"] = project
        long_title = prov.get("long_title")
        ctx["title"] = long_title if long_title else prov["title"]
        ctx["descriptions"] = prov["description"].strip().split(".", 1)
        authors = prov["authors"].strip().split(",", 1)
        ctx["authors"] = {"main": authors[0].strip()}
        if len(authors) > 1:
            ctx["authors"]["etal"] = authors[1].strip()
        ctx["references"] = prov["references"]
        other = prov.get("other", "")
        if other:
            ctx["other"] = j2h.convert(
                json=remap(other, visit=visit),
                table_attributes='class="table is-narrow is-fullwidth has-background-light"',
            )
        if prov["columns"]:
            ctx["columns"] = ["identifier", "id", "formula"] + [
                col["path"]
                if col["unit"] == "NaN"
                else f'{col["path"]} [{col["unit"]}]'
                for col in prov["columns"]
            ]
            ctx["search_columns"] = ["identifier", "formula"] + [
                col["path"]
                for col in prov["columns"]
                if col["unit"] == "NaN" and col["path"] not in ["structures", "tables"]
            ]
            ctx["ranges"] = json.dumps(
                {
                    f'{col["path"]} [{col["unit"]}]': [col["min"], col["max"]]
                    for col in prov["columns"]
                    if col["unit"] != "NaN"
                }
            )

    except Exception as ex:
        ctx["alert"] = str(ex)

    templates = [f"{project}_index.html", "landingpage.html"]
    template = select_template(templates)
    return HttpResponse(template.render(ctx.flatten(), request))


def index(request):
    ctx = get_context(request)
    cname = os.environ["PORTAL_CNAME"]
    template_dir = get_app_template_dirs("templates/notebooks")[0]
    htmls = os.path.join(template_dir, cname, "*.html")
    ctx["notebooks"] = [
        p.split("/" + cname + "/")[-1].replace(".html", "") for p in glob(htmls)
    ]
    ctx["PORTAL_CNAME"] = cname
    ctx["landing_pages"] = []
    mask = ["name", "title", "authors", "is_public", "description", "references"]
    client = Client(headers=get_consumer(request))
    entries = client.projects.get_entries(_fields=mask).result()["data"]
    for entry in entries:
        authors = entry["authors"].strip().split(",", 1)
        if len(authors) > 1:
            authors[1] = authors[1].strip()
        entry["authors"] = authors
        entry["description"] = entry["description"].split(".", 1)[0] + "."
        # visibility governed by is_public flag and X-Consumer-Groups header
        ctx["landing_pages"].append(entry)
    return render(request, "home.html", ctx.flatten())


def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = "basic"
    return html_exporter.from_notebook_node(nb)


def contribution(request, cid):
    ctx = get_context(request)
    client = Client(headers=get_consumer(request))
    contrib = client.contributions.get_entry(
        pk=cid, _fields=["identifier", "notebook"]
    ).result()
    nb = client.notebooks.get_entry(
        pk=contrib["notebook"]["id"], _fields=["_all"]
    ).result()
    ctx["identifier"], ctx["cid"] = contrib["identifier"], cid
    ctx["nb"], _ = export_notebook(nb, cid)
    return render(request, "contribution.html", ctx.flatten())


def download_component(request, oid):
    client = Client(headers=get_consumer(request))
    try:
        resp = client.structures.get_entry(pk=oid, _fields=["cif"]).result()
        content = resp["cif"]
        ext = "cif"
    except HTTPNotFound:
        try:
            resp = client.get_table(oid)
            content = resp.to_csv()
            ext = "csv"
        except HTTPNotFound:
            return HttpResponse(status=404)

    if content:
        content = gzip.compress(bytes(content, "utf-8"))
        response = HttpResponse(content, content_type="application/gzip")
        response["Content-Disposition"] = f"attachment; filename={oid}.{ext}.gz"
        return response

    return HttpResponse(status=404)


def download_contribution(request, cid):
    client = Client(headers=get_consumer(request))
    data = client.contributions.download_entries(
        short_mime="gz", format="json", _fields=["_all"], id=cid
    ).result()
    filename = request.path[1:]
    response = HttpResponse(data, content_type="application/gzip")
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def download(request, project):
    cname = os.environ["PORTAL_CNAME"]
    s3obj = f"{S3_DOWNLOAD_URL}{cname}/{project}.json.gz"
    return redirect(s3obj)
    # TODO check if exists, generate if not, progressbar...
    # return HttpResponse(status=404)


def notebooks(request, nb):
    return render(
        request, os.path.join("notebooks", os.environ["PORTAL_CNAME"], nb + ".html")
    )


def healthcheck(request):
    return HttpResponse("OK")
