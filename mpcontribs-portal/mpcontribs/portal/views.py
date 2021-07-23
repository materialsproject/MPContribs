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
from pathlib import Path
from shutil import make_archive, rmtree
from nbconvert import HTMLExporter
from bravado.exception import HTTPNotFound
from json2html import Json2Html
from boltons.iterutils import remap
from fastnumbers import fast_real
from botocore.errorfactory import ClientError
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.special import TextLexer

from django.shortcuts import render, redirect
from django.template import RequestContext
from django.http import HttpResponse, JsonResponse
from django.template.loaders.app_directories import get_app_template_dirs
from django.template.loader import select_template

from mpcontribs.client import Client, get_md5

CNAME = os.environ.get("PORTAL_CNAME", "contribs.materialsproject.org")
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
    not_logged_in = headers.get("X-Anonymous-Consumer", False)

    if not_logged_in:
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to browse and filter contributions.
        """.strip()

    try:
        with Client(**ckwargs) as client:
            prov = client.projects.get_entry(pk=project, _fields=["_all"]).result()
    except HTTPNotFound:
        msg = f"Project '{project}' not found or access denied!"
        if not_logged_in:
            ctx["alert"] += f" {msg}"
        else:
            ctx["alert"] = msg
    else:
        ctx["name"] = project
        ctx["owner"] = prov["owner"].split(":", 1)[-1]
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
            ctx["components"] = [
                col["path"] for col in prov["columns"] if col["path"] in COMPONENTS
            ]
            ctx["ranges"] = json.dumps(
                {
                    f'{col["path"]} [{col["unit"]}]': [col["min"], col["max"]]
                    for col in prov["columns"]
                    if col["unit"] != "NaN"
                }
            )

    templates = [f"{project}_index.html", "landingpage.html"]
    template = select_template(templates)
    return HttpResponse(template.render(ctx.flatten(), request))


def index(request):
    ctx = get_context(request)
    return render(request, "index.html", ctx.flatten())


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
    ckwargs = client_kwargs(request)

    with Client(**ckwargs) as client:
        entries = client.projects.get_entries(_fields=["_all"]).result()["data"]

    for entry in entries:
        authors = entry["authors"].strip().split(",", 1)
        if len(authors) > 1:
            authors[1] = authors[1].strip()
        entry["authors"] = authors
        entry["description"] = entry["description"].split(".", 1)[0] + "."
        entry["has_data"] = bool(entry.pop("columns"))
        entry["owner"] = entry["owner"].split(":", 1)[-1]
        # visibility governed by is_public flag and X-Authenticated-Groups header
        ctx["landing_pages"].append(entry)
    return render(request, "browse.html", ctx.flatten())


def highlight_code(source, language="python", metadata=None):
    lexer = TextLexer()
    output_formatter = HtmlFormatter(wrapcode=True)
    return highlight(source, lexer, output_formatter)


def export_notebook(nb, cid):
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter()
    html_exporter.template_file = "basic"
    html_exporter.filters["highlight_code"] = highlight_code
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

    with Client(**ckwargs) as client:
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

        nid = contrib["notebook"]["id"]
        try:
            nb = client.notebooks.get_entry(pk=nid, _fields=["_all"]).result()
        except HTTPNotFound:
            return HttpResponse(f"Notebook {nid} not found.", status=404)

        ctx["identifier"], ctx["cid"] = contrib["identifier"], cid
        ctx["nb"], _ = export_notebook(nb, cid)

    return render(request, "contribution.html", ctx.flatten())


def show_component(request, oid):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    resp = None

    if headers.get("X-Anonymous-Consumer", False):
        ctx = get_context(request)
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to show contribution component.
        """.strip()
        return HttpResponse(msg, status=403)

    with Client(**ckwargs) as client:
        try:
            resp = client.get_structure(oid)
        except HTTPNotFound:
            try:
                resp = client.get_table(oid)
            except HTTPNotFound:
                try:
                    resp = client.get_attachment(oid)
                except HTTPNotFound:
                    return HttpResponse(f"Component with ObjectId {oid} not found.", status=404)

    if resp is not None:
        return HttpResponse(resp.info().display())

    return HttpResponse(status=404)


def download_component(request, oid):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    content = None

    if headers.get("X-Anonymous-Consumer", False):
        ctx = get_context(request)
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contribution component.
        """.strip()
        return HttpResponse(msg, status=403)

    with Client(**ckwargs) as client:
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
                    resp = client.get_attachment(oid)
                    name = resp["name"]
                    content = resp.decode()
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
        ctx = get_context(request)
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contribution.
        """.strip()
        return HttpResponse(msg, status=403)

    tmpdir = Path("/tmp")
    outdir = tmpdir / "download"

    with Client(**ckwargs) as client:
        client.download_contributions(
            query={"id": cid}, outdir=outdir, include=list(COMPONENTS)
        )

    zipfile = Path(make_archive(tmpdir / cid, "zip", outdir))
    resp = zipfile.read_bytes()
    rmtree(outdir)
    os.remove(zipfile)
    response = HttpResponse(resp, content_type="application/zip")
    response["Content-Disposition"] = f"attachment; filename={cid}.zip"
    return response


def _get_filename(query, include):
    fn_parts = [query["project"]]
    if include:
        fn_parts.append("-".join(include))
    if [k for k in query.keys() if k != "project"]:
        fn_parts.append(get_md5(query))

    return "_".join(fn_parts)


def _get_download(key, content_type="application/zip"):
    try:
        retr = s3_client.get_object(Bucket=BUCKET, Key=key)
        resp = retr['Body'].read()
    except ClientError:
        return HttpResponse(f"Download {key} not available", status=404)

    filename = os.path.basename(key)
    response = HttpResponse(BytesIO(resp), content_type=content_type)
    response["Content-Disposition"] = f"attachment; filename={filename}"
    response["Content-Length"] = len(resp)
    return response


def _reconcile_include(request, project: str, fields: list):
    ckwargs = client_kwargs(request)
    avail_components = set()

    with Client(**ckwargs) as client:
        info = client.projects.get_entry(pk=project, _fields=["columns"]).result()

    for column in info["columns"]:
        path = column["path"]
        if not path.startswith("data.") and path in COMPONENTS:
            avail_components.add(path)

    return list(set(fields) & avail_components)


def _get_fields_from_params(params):
    for k in ["_fields", "include"]:
        if k in params:
            v = params.pop(k)[0]
            if v:
                return v.split(",")

    return []


def _get_query_include(request):
    params = deepcopy(request.GET)
    fmt = params.pop("format", ["json"])[0]
    fields = _get_fields_from_params(params)
    params.pop("X-API-KEY", None)  # client already initialized through headers
    query = {k: v for k, v in params.items()}
    query["format"] = fmt
    include = _reconcile_include(request, query["project"], fields)
    return query, include


def _get_download_key(query: dict, include: list):
    fn = _get_filename(query, include)
    fmt = query.get("format", "json")
    return f"{CNAME}/{fn}_{fmt}.zip"


def download_project(request, project: str, extension: str):
    if extension == "zip":
        # TODO need to remove zipfile in S3 bucket on API update/save signal
        fmt = request.GET.get("format", "json")
        query = {"project": project, "format": fmt}
        fields = _get_fields_from_params(request.GET)
        include = _reconcile_include(request, project, fields)
        key = _get_download_key(query, include)
        content_type = "application/zip"
    elif extension == "json.gz":
        subdir = "raw" if os.environ.get("TRADEMARK") == "ML" else "without_components"
        key = f"{CNAME}/manual/{subdir}/{project}.json.gz"
        content_type = "application/gzip"
    else:
        return HttpResponse(f"Invalid extension {extension}!", status=400)

    return _get_download(key, content_type=content_type)


def download(request):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    if headers.get("X-Anonymous-Consumer", False):
        ctx = get_context(request)
        msg = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to download contributions.
        """.strip()
        return HttpResponse(msg, status=403)

    project = request.GET.get("project")
    if not project:
        return HttpResponse("Missing project parameter.", status=404)

    query, include = _get_query_include(request)
    key = _get_download_key(query, include)
    return _get_download(key)


def create_download(request):
    ckwargs = client_kwargs(request)
    headers = ckwargs.get("headers", {})
    if headers.get("X-Anonymous-Consumer", False):
        return JsonResponse({"error": "Permission denied."}, status=403)

    project = request.GET.get("project")
    if not project:
        return JsonResponse({"error": "Missing project parameter."})

    query, include = _get_query_include(request)
    key = _get_download_key(query, include)

    with Client(**ckwargs) as client:
        total_count, total_pages = client.get_totals(query=query, op="download")

        if total_count < 1:
            return JsonResponse({"error": "No results for query."})

        last_modified = client.contributions.get_entries(
            order="desc", _order_by="last_modified",
            _fields=["last_modified"], _limit=1,
            **{k: v for k, v in query.items() if k != "format"}
        ).result()["data"][0]["last_modified"]

        try:
            s3_client.head_object(Bucket=BUCKET, Key=key, IfModifiedSince=last_modified)
        except ClientError:
            all_ids = client.get_all_ids(
                query=query, include=include, timeout=20
            ).get(project)
            if not all_ids:
                return JsonResponse({"error": "No results for query."})

            ncontribs = len(all_ids["ids"])

            if ncontribs < total_count:
                # timeout reached -> use API/client
                return JsonResponse({
                    "error": "Too many contributions matching query. Use API/client."
                })

            all_files = total_pages  # for contributions
            for component in include:
                ncomp = len(all_ids[component]["ids"])
                per_page, _ = client._get_per_page_default_max(
                    op="download", resource=component
                )
                all_files += int(ncomp / per_page) + bool(ncomp % per_page)

            fn = _get_filename(query, include)
            tmpdir = Path("/tmp")
            outdir = tmpdir / fn
            existing_files = sum(len(files) for _, _, files in os.walk(outdir))
            ndownloads = client.download_contributions(
                query=query, include=include, outdir=outdir, timeout=30
            )
            total_files = existing_files + ndownloads

            if total_files < all_files:
                return JsonResponse({"progress": total_files/all_files})

            make_archive(outdir, "zip", outdir)
            zipfile = outdir.with_suffix(".zip")
            resp = zipfile.read_bytes()
            s3_client.put_object(
                Bucket=BUCKET, Key=key, Body=resp,
                ContentType="application/zip"
            )
            rmtree(outdir)
            os.remove(zipfile)

    return JsonResponse({"progress": 1})


def notebooks(request, nb):
    subdir = os.environ["PORTAL_CNAME"].replace("localhost.", "")
    return render(request, os.path.join("notebooks", subdir, nb + ".html"))


def healthcheck(request):
    return HttpResponse("OK")
