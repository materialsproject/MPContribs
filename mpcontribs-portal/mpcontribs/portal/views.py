# -*- coding: utf-8 -*-
"""This module provides the views for the portal."""

import os
import gzip
import json
import boto3
import nbformat
import requests

from io import BytesIO
from copy import deepcopy
from glob import glob
from nbconvert import HTMLExporter
from bravado.exception import HTTPNotFound
from json2html import Json2Html
from boltons.iterutils import remap
from fastnumbers import fast_real
from base64 import b64decode
from botocore.errorfactory import ClientError

from django.shortcuts import render, redirect
from django.template import RequestContext
from django.http import HttpResponse
from django.template.loaders.app_directories import get_app_template_dirs
from django.template.loader import select_template

from mpcontribs.client import Client

BUCKET = os.environ.get("S3_DOWNLOADS_BUCKET", "mpcontribs-downloads")
COMPONENTS = {"structures", "tables", "attachments"}
j2h = Json2Html()
s3_client = boto3.client('s3')


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return key not in ["value", "unit"]


def get_consumer(request):
    names = [
        "X-Authenticated-Groups", "X-Consumer-Groups",
        "X-Consumer-Username", "X-Anonymous-Consumer"
    ]
    headers = {}
    for name in names:
        key = f'HTTP_{name.upper().replace("-", "_")}'
        value = request.META.get(key)
        if value is not None:
            headers[name] = value
    return headers


def client_kwargs(request):
    return {"headers": get_consumer(request)}


def get_context(request):
    ctx = RequestContext(request)
    ctx["API_CNAME"] = os.environ["API_CNAME"]
    ctx["TRADEMARK"] = os.environ.get("TRADEMARK", "")
    ctx["PORTAL_CNAME"] = os.environ["PORTAL_CNAME"]
    localhost = ctx["PORTAL_CNAME"].startswith("localhost.")
    ctx["OAUTH_URL"] = "http://localhost." if localhost else "https://"
    ctx["OAUTH_URL"] += "profile.materialsproject.org"
    return ctx


def landingpage(request, project):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    ctx = get_context(request)

    if headers.get("X-Anonymous-Consumer", False):
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to browse and filter contributions.
        """.strip()

    try:
        client = Client(**ckwargs)
        prov = client.projects.get_entry(pk=project, _fields=["_all"]).result()
        ctx["name"] = project
        long_title = prov.get("long_title")
        ctx["title"] = long_title if long_title else prov["title"]
        ctx["descriptions"] = prov["description"].strip().split(".", 1)
        authors = prov["authors"].strip().split(",", 1)
        ctx["authors"] = {"main": authors[0].strip()}
        if len(authors) > 1:
            ctx["authors"]["etal"] = authors[1].strip()
        ctx["references"] = prov["references"][:5]
        ctx["more_references"] = prov["references"][5:]
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
                if col["unit"] == "NaN" and col["path"] not in COMPONENTS
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
    return render(request, "index.html", ctx.flatten())


def work(request):
    ctx = get_context(request)
    template_dir = get_app_template_dirs("templates/notebooks")[0]
    subdir = ctx["PORTAL_CNAME"].replace("localhost.", "")
    htmls = os.path.join(template_dir, subdir, "*.html")
    ctx["notebooks"] = [
        p.split("/" + subdir + "/")[-1].replace(".html", "")
        for p in glob(htmls)
    ]
    return render(request, "work.html", ctx.flatten())


def search(request):
    headers = client_kwargs(request).get("headers", {})
    ctx = get_context(request)

    if headers.get("X-Anonymous-Consumer", False):
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to search contributions.
        """.strip()

    return render(request, "search.html", ctx.flatten())


def apply(request):
    headers = client_kwargs(request).get("headers", {})
    ctx = get_context(request)

    if headers.get("X-Anonymous-Consumer", False):
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to apply for a project.
        """.strip()

    return render(request, "apply.html", ctx.flatten())


def browse(request):
    ctx = get_context(request)
    ctx["landing_pages"] = []
    mask = ["name", "title", "authors", "is_public", "description", "references"]
    client = Client(**client_kwargs(request))
    entries = client.projects.get_entries(_fields=mask).result()["data"]
    for entry in entries:
        authors = entry["authors"].strip().split(",", 1)
        if len(authors) > 1:
            authors[1] = authors[1].strip()
        entry["authors"] = authors
        entry["description"] = entry["description"].split(".", 1)[0] + "."
        # visibility governed by is_public flag and X-Authenticated-Groups header
        ctx["landing_pages"].append(entry)
    return render(request, "browse.html", ctx.flatten())


def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = "basic"
    return html_exporter.from_notebook_node(nb)


def contribution(request, cid):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    ctx = get_context(request)

    if headers.get("X-Anonymous-Consumer", False):
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to view contribution.
        """.strip()
        return render(request, "contribution.html", ctx.flatten())

    client = Client(**ckwargs)
    try:
        contrib = client.contributions.get_entry(
            pk=cid, _fields=["identifier", "notebook"]
        ).result()
    except HTTPNotFound:
        return HttpResponse(f"Contribution {cid} not found.", status=404)

    if "notebook" not in contrib:
        url = f"{client.url}/notebooks/build"
        r = requests.get(url, params={"cids": cid})
        if r.status_code == requests.codes.ok:
            contrib = client.contributions.get_entry(
                pk=cid, _fields=["identifier", "notebook"]
            ).result()
        else:
            ctx["alert"] = f"Notebook build failed with status {r.status_code}"
            return render(request, "contribution.html", ctx.flatten())

    nid = contrib["notebook"]
    try:
        nb = client.notebooks.get_entry(pk=nid, _fields=["_all"]).result()
    except HTTPNotFound:
        return HttpResponse(f"Notebook {nid} not found.", status=404)

    ctx["identifier"], ctx["cid"] = contrib["identifier"], cid
    ctx["nb"], _ = export_notebook(nb, cid)
    return render(request, "contribution.html", ctx.flatten())


def download_component(request, oid):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    if headers.get("X-Anonymous-Consumer", False):
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contribution component.
        """.strip()
        return HttpResponse(msg, status=403)

    content = None
    client = Client(**ckwargs)
    try:
        resp = client.structures.get_entry(pk=oid, _fields=["name", "cif"]).result()
        name = resp["name"]
        content = gzip.compress(bytes(resp["cif"], "utf-8"))
        content_type = "application/gzip"
        filename = f"{oid}_{name}.cif.gz"
    except HTTPNotFound:
        try:
            resp = client.get_table(oid)
            content = gzip.compress(bytes(resp.to_csv(), "utf-8"))
            resp = client.tables.get_entry(pk=oid, _fields=["name"]).result()
            name = resp["name"]
            content_type = "application/gzip"
            filename = f"{oid}_{name}.csv.gz"
        except HTTPNotFound:
            try:
                resp = client.attachments.get_entry(pk=oid, _fields=["_all"]).result()
                name = resp["name"]
                content = b64decode(resp["content"], validate=True)
                content_type = resp["mime"]
                filename = f"{oid}_{name}"
            except HTTPNotFound:
                return HttpResponse(f"Component with ObjectId {oid} not found.", status=404)

    if content:
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f"attachment; filename={filename}"
        return response

    return HttpResponse(status=404)


def download_contribution(request, cid):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    if headers.get("X-Anonymous-Consumer", False):
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contribution.
        """.strip()
        return HttpResponse(msg, status=403)

    client = Client(**ckwargs)
    resp = client.contributions.get_entry(pk=cid, _fields=["project"]).result()
    resp = client.projects.get_entry(pk=resp["project"], _fields=["columns"]).result()
    fields = ["project", "identifier", "formula", "is_public", "last_modified"]
    fields += [
        column["path"] + ".display"
        for column in resp["columns"]
        if column["path"].startswith("data.")
    ]
    fields += list(COMPONENTS)
    resp = client.contributions.download_entries(
        id=cid, short_mime="gz", format="json", _fields=fields
    ).result()
    filename = request.path[1:]
    response = HttpResponse(resp, content_type="application/gzip")
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def download_project(request, project):
    # NOTE separate original uploads for ML deployment
    # TODO enable choice to download full dataset ("manual/with_components/{project}.json.gz")
    subdir = "raw" if os.environ.get("TRADEMARK") == "ML" else "without_components"
    cname = os.environ["PORTAL_CNAME"]
    key = f"{cname}/manual/{subdir}/{project}.json.gz"

    try:
        retr = s3_client.get_object(Bucket=BUCKET, Key=key)
        buffer = BytesIO(retr['Body'].read())
        return HttpResponse(buffer, content_type="application/gzip")
    except ClientError:
        return HttpResponse(status=404)


def download(request):
    if not request.GET:
        return HttpResponse("Only GET requests allowed.", status=405)

    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    if headers.get("X-Anonymous-Consumer", False):
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contribution.
        """.strip()
        return HttpResponse(msg, status=403)

    required_params = {"project", "format", "_fields"}
    if not required_params.issubset(request.GET.keys()):
        return HttpResponse("Missing parameters.", status=400)

    client = Client(**ckwargs)
    params = deepcopy(request.GET)
    fmt = params.pop("format")[0]
    fields = params.pop("_fields")[0].split(",")

    kwargs = {"fields": ["id"]}
    for k, v in params.items():
        kwargs[k] = fast_real(v)

    resp = client.contributions.get_entries(**kwargs).result()

    if resp["total_count"] < 1:
        return HttpResponse("No contributions found.", status=404)
    elif resp["total_count"] > 1000:
        return HttpResponse("Please limit query to less than 1000 contributions.", status=403)

    kwargs = {"_fields": fields, "format": fmt, "short_mime": "gz"}
    for k, v in params.items():
        kwargs[k] = v

    resp = client.contributions.download_entries(**kwargs).result()
    filename = f'{kwargs["project"]}.{fmt}.gz'
    response = HttpResponse(resp, content_type="application/gzip")
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def notebooks(request, nb):
    subdir = os.environ["PORTAL_CNAME"].replace("localhost.", "")
    return render(request, os.path.join("notebooks", subdir, nb + ".html"))


def healthcheck(request):
    return HttpResponse("OK")
