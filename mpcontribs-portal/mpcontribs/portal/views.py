# -*- coding: utf-8 -*-
"""This module provides the views for the portal."""

import os
import json
import nbformat
from glob import glob
from nbconvert import HTMLExporter
from bs4 import BeautifulSoup
from fido.exceptions import HTTPTimeoutError

from django.shortcuts import render, redirect
from django.template import RequestContext
from django.http import HttpResponse
from django.template.loaders.app_directories import get_app_template_dirs
from django.template.loader import select_template

from mpcontribs.client import load_client
from mpcontribs.io.core.components.hdata import HierarchicalData

# TODO should not be needed if render_json.js took care of display/unit/value

S3_DOWNLOADS_BUCKET = os.environ.get("S3_DOWNLOADS_BUCKET", "mpcontribs-downloads")
S3_DOWNLOAD_URL = f"https://{S3_DOWNLOADS_BUCKET}.s3.amazonaws.com/"


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
        client = load_client(headers=get_consumer(request))
        prov = client.projects.get_entry(pk=project, _fields=["_all"]).result()
        ctx["project"] = project
        long_title = prov.get("long_title")
        ctx["title"] = long_title if long_title else prov["title"]
        ctx["descriptions"] = prov["description"].strip().split(".", 1)
        authors = prov["authors"].strip().split(",", 1)
        ctx["authors"] = {"main": authors[0].strip()}
        if len(authors) > 1:
            ctx["authors"]["etal"] = authors[1].strip()
        ctx["urls"] = prov["urls"]
        other = prov.get("other", "")
        if other:
            ctx["other"] = json.dumps(HierarchicalData(other))
        if prov["columns"]:
            ctx["columns"] = ["identifier", "id", "formula"] + list(
                prov["columns"].keys()
            )
            ctx["search_columns"] = ["identifier", "formula"] + [
                col
                for col in prov["columns"].keys()
                if not col.endswith("]") and not col.startswith("structures")
            ]
            ctx["ranges"] = json.dumps(prov["columns"])

        # TODO contribs key is only used in dilute_diffusion and should go through the table
        # from mpcontribs.io.core.utils import get_short_object_id
        # ctx['contribs'] = []
        # for contrib in client.contributions.get_entries(
        #    project=project, _fields=['id', 'identifier', 'data.formula']
        # ).result()['data']:
        #    formula = contrib.get('data', {}).get('formula')
        #    if formula:
        #        contrib['formula'] = formula
        #        contrib['short_cid'] = get_short_object_id(contrib['id'])
        #        ctx['contribs'].append(contrib)
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
    mask = ["project", "title", "authors", "is_public", "description", "urls"]
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    entries = client.projects.get_entries(_fields=mask).result()["data"]
    for entry in entries:
        authors = entry["authors"].strip().split(",", 1)
        if len(authors) > 1:
            authors[1] = authors[1].strip()
        entry["authors"] = authors
        entry["description"] = entry["description"].split(".", 1)[0] + "."
        ctx["landing_pages"].append(
            entry
        )  # visibility governed by is_public flag and X-Consumer-Groups header
    return render(request, "home.html", ctx.flatten())


def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = "basic"
    body = html_exporter.from_notebook_node(nb)[0]
    soup = BeautifulSoup(body, "html.parser")
    # mark cells with special name for toggling, and
    # TODO make element id's unique by appending cid (for ingester)
    for div in soup.find_all("div", "output_wrapper"):
        script = div.find("script")
        if script:
            script = script.contents[0]
            if script.startswith("render_json"):
                div["name"] = "HData"
            elif script.startswith("render_table"):
                div["name"] = "Tables"
            elif script.startswith("render_plot"):
                div["name"] = "Graphs"
        else:
            pre = div.find("pre")
            if pre and pre.contents[0].startswith("Structure"):
                div["name"] = "Structures"
    # name divs for toggling code_cells
    for div in soup.find_all("div", "input"):
        div["name"] = "Code"
    # separate script
    script = []
    for s in soup.find_all("script"):
        script.append(s.string)
        s.extract()  # remove javascript
    return soup.prettify(), "\n".join(script)


def contribution(request, cid):
    ctx = get_context(request)
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contrib = client.contributions.get_entry(
        pk=cid, _fields=["id", "identifier"]
    ).result()
    ctx["identifier"], ctx["cid"] = contrib["identifier"], contrib["id"]
    nb = client.notebooks.get_entry(pk=cid).result()  # generate notebook with cells
    ctx["ncells"] = len(nb["cells"])

    if not nb["cells"][-1]["outputs"]:
        try:
            nb = client.notebooks.get_entry(pk=cid).result(
                timeout=1
            )  # trigger cell execution
        except HTTPTimeoutError as e:
            dots = '<span class="loader__dot">.</span><span class="loader__dot">.</span><span class="loader__dot">.</span>'
            ctx["alert"] = f"Detail page is building in the background {dots}"

    ctx["nb"], ctx["js"] = export_notebook(nb, cid)
    return render(request, "contribution.html", ctx.flatten())


def cif(request, sid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    cif = client.structures.get_entry(pk=sid, _fields=["cif"]).result()["cif"]
    if cif:
        response = HttpResponse(cif, content_type="text/plain")
        response["Content-Disposition"] = "attachment; filename={}.cif".format(sid)
        return response
    return HttpResponse(status=404)


def download_json(request, cid):
    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contrib = client.contributions.get_entry(pk=cid, fields=["_all"]).result()
    if contrib:
        jcontrib = json.dumps(contrib)
        response = HttpResponse(jcontrib, content_type="application/json")
        response["Content-Disposition"] = "attachment; filename={}.json".format(cid)
        return response
    return HttpResponse(status=404)


def csv(request, project):
    from pandas import DataFrame
    from pandas.io.json._normalize import nested_to_record

    client = load_client(headers=get_consumer(request))  # sets/returns global variable
    contribs = client.contributions.get_entries(
        project=project, _fields=["identifier", "id", "formula", "data"]
    ).result()[
        "data"
    ]  # first 20 only

    data = []
    for contrib in contribs:
        data.append({})
        for k, v in nested_to_record(contrib, sep=".").items():
            if v is not None and not k.endswith(".value") and not k.endswith(".unit"):
                vs = v.split(" ")
                if k.endswith(".display") and len(vs) > 1:
                    key = k.replace("data.", "").replace(".display", "") + f" [{vs[1]}]"
                    data[-1][key] = vs[0]
                else:
                    data[-1][k] = v

    df = DataFrame(data)
    response = HttpResponse(df.to_csv(), content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename={}.csv".format(project)
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
