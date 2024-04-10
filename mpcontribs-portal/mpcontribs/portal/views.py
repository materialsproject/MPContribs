# -*- coding: utf-8 -*-
"""This module provides the views for the portal."""

import os
import gzip
import json
import boto3
import nbformat
import requests
import urllib

from redis import Redis
from io import BytesIO
from copy import deepcopy
from pathlib import Path
from shutil import make_archive, rmtree
from nbconvert import HTMLExporter
from bravado.exception import HTTPNotFound
from json2html import Json2Html
from boltons.iterutils import remap
from botocore.errorfactory import ClientError
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.special import TextLexer

from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse, JsonResponse
from django.template.loader import select_template

from mpcontribs.client import Client, get_md5

BUCKET = os.environ.get("S3_DOWNLOADS_BUCKET", "mpcontribs-downloads")
COMPONENTS = {"structures", "tables", "attachments"}
j2h = Json2Html()
s3_client = boto3.client("s3")
lambda_client = boto3.client("lambda")
redis_store = Redis.from_url(
    "redis://" + os.environ["REDIS_ADDRESS"], decode_responses=True
)


def visit(path, key, value):
    if isinstance(value, dict) and "display" in value:
        return key, value["display"]
    return key not in ["value", "unit"]


def get_consumer(request):
    names = [
        "X-Authenticated-Groups",
        "X-Consumer-Groups",
        "X-Consumer-Username",
        "X-Anonymous-Consumer",
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
    parsed_url = urllib.parse.urlparse(request.build_absolute_uri())
    ctx["TRADEMARK"] = os.environ.get("TRADEMARK", "")
    is_localhost = parsed_url.netloc.startswith("localhost.")
    parts = parsed_url.netloc.split(".")
    subdomain_index = 1 if is_localhost else 0
    subdomain = parts[subdomain_index]
    preview_suffix = "-preview"
    is_preview = subdomain.endswith(preview_suffix)
    api_subdomain = subdomain.replace(preview_suffix, "")
    api_subdomain += "-api"

    if is_preview:
        api_subdomain += preview_suffix

    new_parts = ["localhost"] if is_localhost else []
    new_parts.append(api_subdomain)
    new_parts += parts[subdomain_index + 1 :]
    ctx["API_CNAME"] = ".".join(new_parts)

    scheme = "http" if is_localhost else "https"
    netloc = "localhost." if is_localhost else ""
    netloc += "profile.materialsproject.org"
    ctx["OAUTH_URL"] = f"{scheme}://{netloc}"
    return ctx


def landingpage(request, project):
    ckwargs = client_kwargs(request)
    ctx = get_context(request)

    try:
        client = Client(**ckwargs)
        prov = client.get_project(project)
    except HTTPNotFound:
        ctx["alert"] = f"Project '{project}' not found or access denied! Try to log in."
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
        ctx["license"] = prov.get("license", "CCA4")
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
    return render(request, "browse.html", ctx.flatten())


def search(request):
    ctx = get_context(request)
    return render(request, "search.html", ctx.flatten())


def apply(request):
    headers = client_kwargs(request).get("headers", {})
    ctx = get_context(request)

    if headers.get("X-Anonymous-Consumer", False):
        ctx["alert"] = f"""
        Please <a href=\"{ctx['OAUTH_URL']}\">log in</a> to apply for a project.
        """.strip()

    return render(request, "apply.html", ctx.flatten())


def highlight_code(source, language="python", metadata=None):
    lexer = TextLexer()
    output_formatter = HtmlFormatter(wrapcode=True)
    return highlight(source, lexer, output_formatter)


def export_notebook(nb, cid):
    nb.pop("id")
    nb = nbformat.from_dict(nb)
    html_exporter = HTMLExporter(template_name="basic")
    html_exporter.filters["highlight_code"] = highlight_code
    return html_exporter.from_notebook_node(nb)


def contribution(request, cid):
    ckwargs = client_kwargs(request)
    ctx = get_context(request)
    client = Client(**ckwargs)

    try:
        contrib = client.contributions.getContributionById(
            pk=cid, _fields=["identifier", "needs_build", "notebook"]
        ).result()
    except HTTPNotFound:
        return HttpResponse(f"Contribution {cid} not found.", status=404)

    if "notebook" not in contrib or contrib.get("needs_build", True):
        url = f"{client.url}/notebooks/build"
        r = requests.get(url, params={"cids": cid, "force": True})
        if r.status_code == requests.codes.ok:
            status = r.json().get("result", {}).get("status")
            if status != "COMPLETED":
                ctx["alert"] = f"Notebook build failed with status {status}"
                return render(request, "contribution.html", ctx.flatten())

            contrib = client.contributions.getContributionById(
                pk=cid, _fields=["identifier", "notebook"]
            ).result()
        else:
            ctx["alert"] = f"Notebook build failed with status {r.status_code}"
            return render(request, "contribution.html", ctx.flatten())

    nid = contrib["notebook"]["id"]
    try:
        nb = client.notebooks.getNotebookById(pk=nid, _fields=["_all"]).result()
    except HTTPNotFound:
        return HttpResponse(f"Notebook {nid} not found.", status=404)

    ctx["identifier"], ctx["cid"] = contrib["identifier"], cid
    ctx["nb"], _ = export_notebook(nb, cid)

    return render(request, "contribution.html", ctx.flatten())


def show_component(request, oid):
    ckwargs = client_kwargs(request)
    resp = None
    client = Client(**ckwargs)

    try:
        resp = client.get_structure(oid)
    except HTTPNotFound:
        try:
            resp = client.get_table(oid)
        except HTTPNotFound:
            try:
                resp = client.get_attachment(oid)
            except HTTPNotFound:
                return HttpResponse(
                    f"Component with ObjectId {oid} not found.", status=404
                )

    if resp is not None:
        return HttpResponse(resp.info().display())

    return HttpResponse(status=404)


def download_component(request, oid):
    ckwargs = client_kwargs(request)
    content = None
    client = Client(**ckwargs)

    try:
        resp = client.structures.getStructureById(
            pk=oid, _fields=["name", "cif"]
        ).result()
        name = resp["name"]
        content = gzip.compress(bytes(resp["cif"], "utf-8"))
        content_type = "application/gzip"
        filename = f"{oid}_{name}.cif.gz"
    except HTTPNotFound:
        try:
            resp = client.get_table(oid)
            content = gzip.compress(bytes(resp.to_csv(), "utf-8"))
            resp = client.tables.getTableById(pk=oid, _fields=["name"]).result()
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
                return HttpResponse(
                    f"Component with ObjectId {oid} not found.", status=404
                )

    if content:
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f"attachment; filename={filename}"
        return response

    return HttpResponse(status=404)


def download_contribution(request, cid):
    client = Client(**client_kwargs(request))
    # NOTE gevent and FuturesSession don't play nice -> use query_contributions for now
    # TODO might need to switch client to use httpx instead of requests_futures
    contributions = client.query_contributions(query={"id": cid}, fields=["_all"])
    if not contributions:
        return HttpResponse(status=404)

    contribution = contributions["data"][0]
    for k in ["card_bulma", "card_bootstrap", "notebook", "needs_build"]:
        if k in contribution:
            contribution.pop(k)

    for component in COMPONENTS:
        comp_list = contribution.pop(component, [])
        if comp_list:
            resource = getattr(client, component)
            func = f"get{component[:-1].capitalize()}ById"
            getComponentById = getattr(resource, func)

            for item in comp_list:
                if item.get("id"):
                    contribution[component] = getComponentById(
                        pk=item["id"], _fields=["_all"]
                    ).result()

    encoded = json.dumps(contribution, default=str, indent=2).encode("utf-8")
    content = gzip.compress(encoded)
    response = HttpResponse(content, content_type="application/gzip")
    response["Content-Disposition"] = f"attachment; filename={cid}.json.gz"
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
        resp = retr["Body"].read()
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
    client = Client(**ckwargs)
    info = client.projects.getProjectByName(pk=project, _fields=["columns"]).result()

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
    return f"{fn}_{fmt}.zip"


def download_project(request, project: str, extension: str):
    if extension == "zip":
        fmt = request.GET.get("format", "json")
        query = {"project": project, "format": fmt}
        fields = _get_fields_from_params(request.GET)
        include = _reconcile_include(request, project, fields)
        key = _get_download_key(query, include)
        content_type = "application/zip"
    elif extension == "json.gz":
        subdir = "raw" if os.environ.get("TRADEMARK") == "ML" else "without_components"
        key = f"manual/{subdir}/{project}.json.gz"
        content_type = "application/gzip"
    else:
        return HttpResponse(f"Invalid extension {extension}!", status=400)

    return _get_download(key, content_type=content_type)


def download(request):
    ckwargs = client_kwargs(request)
    project = request.GET.get("project")
    if not project:
        return HttpResponse("Missing project parameter.", status=404)

    query, include = _get_query_include(request)
    key = _get_download_key(query, include)
    return _get_download(key)


def create_download(request):
    ckwargs = client_kwargs(request)
    project = request.GET.get("project")
    if not project:
        return JsonResponse({"error": "Missing project parameter."})

    query, include = _get_query_include(request)
    headers = ckwargs.get("headers", {})
    return make_download(headers, query, include)


def make_download(headers, query, include=None):
    client = Client(headers=headers)
    include = include or []
    key = _get_download_key(query, include)
    total_count, total_pages = client.get_totals(query=query, op="download")

    if total_count < 1:
        return JsonResponse({"error": "No results for query."})

    kwargs = {
        k: v
        for k, v in query.items()
        if k not in {"format", "_sort", "_fields", "_limit", "per_page"}
    }
    last_modified = client.contributions.queryContributions(
        _sort="-last_modified", _fields=["last_modified"], _limit=1, **kwargs
    ).result()["data"][0]["last_modified"]
    json_resp = {"status": "UNDEFINED"}

    try:
        s3_client.head_object(Bucket=BUCKET, Key=key, IfModifiedSince=last_modified)
        json_resp["status"] = "READY"  # latest version already generated
    except ClientError:
        try:
            s3_resp = s3_client.head_object(Bucket=BUCKET, Key=key)
            next_version = int(s3_resp["Metadata"].get("version", 1)) + 1
        except ClientError:
            next_version = 1  # about to generate first version

        filename = _get_filename(query, include)
        fmt = query.get("format", "json")
        redis_key = f"{BUCKET}:{filename}:{fmt}:{next_version}"
        json_resp["redis_key"] = redis_key
        status = redis_store.get(redis_key)

        if status is None:
            payload = {
                "redis_key": redis_key,
                "host": os.environ["MPCONTRIBS_CLIENT_HOST"],
                "headers": headers,
                "query": query,
                "include": include,
            }
            try:
                response = lambda_client.invoke(
                    FunctionName="mpcontribs-make-download",
                    InvocationType="Event",
                    Payload=json.dumps(payload),
                )
                if response["StatusCode"] == 202:
                    status = "SUBMITTED"
                    json_resp["status"] = status
                    redis_store.set(redis_key, status)
                else:
                    status = "ERROR"
                    json_resp["status"] = status
                    json_resp["error"] = "Failed to queue download request"
                    redis_store.set(redis_key, status)
            except Exception as e:
                status = "ERROR"
                json_resp["status"] = status
                json_resp["error"] = str(e)
                redis_store.set(redis_key, status)
        else:
            json_resp["status"] = status

    return JsonResponse(json_resp)


def healthcheck(request):
    return HttpResponse("OK")
