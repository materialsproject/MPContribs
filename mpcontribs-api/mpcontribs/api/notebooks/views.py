# -*- coding: utf-8 -*-
import os
import time
import requests
import flask_mongorest

from rq import get_current_job
from rq.job import Job
from gevent import sleep
from nbformat import v4 as nbf
from flask_rq2 import RQ
from flask import Blueprint, request, abort, jsonify, current_app
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch
from flask_mongorest.resources import Resource
from mongoengine.errors import DoesNotExist
from mongoengine.queryset.visitor import Q

from mpcontribs.api import get_kernel_endpoint, get_logger
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.notebooks import run_cells


logger = get_logger(__name__)
templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)

MPCONTRIBS_API_HOST = os.environ.get("MPCONTRIBS_API_HOST", "default")
ADMIN_GROUP = os.environ.get("ADMIN_GROUP", "admin")

rq = RQ()
rq.default_queue = f"notebooks_{MPCONTRIBS_API_HOST}"
rq.queues = [rq.default_queue]


class NotebooksResource(Resource):
    document = Notebooks
    filters = {"id": [ops.In, ops.Exact]}
    fields = ["id", "nbformat", "nbformat_minor"]
    paginate = True
    default_limit = 10
    max_limit = 100

    @staticmethod
    def get_optional_fields():
        return ["metadata", "cells"]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch, BulkFetch]


def execute_cells(cid, cells):
    ntries = 0
    while ntries < 5:
        for kernel_id, running_cid in current_app.kernels.items():
            if running_cid is None:
                current_app.kernels[kernel_id] = cid
                try:
                    outputs = run_cells(kernel_id, cid, cells)
                except:
                    current_app.kernels[kernel_id] = None
                    raise

                current_app.kernels[kernel_id] = None
                return outputs
            else:
                logger.warning(f"{kernel_id} busy with {running_cid}")

        logger.warning("WAITING for a kernel to become available")
        sleep(5)
        ntries += 1


@notebooks.route("/build")
def build():
    if not getattr(current_app, "kernels", None):
        abort(404, description="No kernels available.")

    cids = request.args.get("cids")
    projects = request.args.get("projects")
    force = bool(request.args.get("force", 0))
    kwargs = dict(force=force)

    if projects:
        kwargs["projects"] = projects.split(",")

    if cids:
        kwargs["cids"] = cids.split(",")

    if len(kwargs.get("cids", [])) == 1:
        return jsonify(make(**kwargs))

    job = make.queue(**kwargs)
    return job.id


def restart_kernels():
    """use to avoid run-away memory"""
    kernel_ids = [k for k, v in current_app.kernels.items() if v is None]

    for kernel_id in kernel_ids:
        kernel_url = get_kernel_endpoint(kernel_id) + "/restart"
        requests.post(kernel_url, json={})
        cells = [nbf.new_code_cell("\n".join([
            "from mpcontribs.client import Client",
            "print('client imported')"
        ]))]
        run_cells(kernel_id, "import_client", cells)


@notebooks.route('/result', defaults={'job_id': None})
@notebooks.route("/result/<job_id>")
def result(job_id):
    if not current_app.kernels:
        abort(404, description="No kernels available.")

    if not job_id:
        job_id = f"cron-{current_app.cron_job_id}"

    try:
        job = Job.fetch(job_id, connection=rq.connection)
    except Exception as exception:
        abort(404, description=exception)

    if not job.is_finished:
        return job.get_status()
    elif not job.result:
        description = f"No result for job_id {job.id} (exc: {job.exc_info})."
        abort(404, description=description)

    return jsonify(job.result)


@rq.job()
def make(projects=None, cids=None, force=False):
    """build the notebook / details page"""
    start = time.perf_counter()
    remaining_time = rq.default_timeout - 5
    mask = ["id", "needs_build", "notebook"]
    query = _build_query(projects, cids, force)

    job = get_current_job()
    ret = {"input": {"projects": projects, "cids": cids, "force": force}}
    if job:
        ret["job"] = {
            "id": job.id,
            "enqueued_at": job.enqueued_at.isoformat(),
            "started_at": job.started_at.isoformat()
        }

    exclude = list(Contributions._fields.keys())
    documents = Contributions.objects(query).exclude(*exclude).only(*mask)
    total = documents.count()
    count = 0

    for idx, document in enumerate(documents):
        stop = time.perf_counter()
        remaining_time -= stop - start

        if remaining_time < 0:
            if job:
                restart_kernels()

            ret["result"] = {"status": "TIMEOUT", "count": count, "total": total}
            return ret

        start = time.perf_counter()

        if not force and document.notebook and \
                not getattr(document, "needs_build", True):
            continue

        _handle_document_notebook(document)

        cid = str(document.id)
        logger.debug(f"prep notebook for {cid} ...")
        document.reload("tables", "structures", "attachments")

        cells = [
            # define client only once in kernel
            # avoids API calls for regex expansion for query parameters
            nbf.new_code_cell("\n".join([
                "if 'client' not in locals():",
                "\tclient = Client(",
                f'\t\theaders={{"X-Authenticated-Groups": "{ADMIN_GROUP}"}},',
                f'\t\thost="{MPCONTRIBS_API_HOST}"',
                "\t)",
                "print(client.get_totals())",
                # return something. See while loop in `run_cells`
            ])),
            nbf.new_code_cell("\n".join([
                f'c = client.get_contribution("{document.id}")',
                'c.display()'
            ])),
        ]

        _handle_document_tables(document, cells)

        _handle_document_structures(document, cells)

        _handle_document_attachmentss(document, cells)

        try:
            outputs = execute_cells(cid, cells)
        except Exception as e:
            if job:
                restart_kernels()

            ret["result"] = {
                "status": "ERROR", "cid": cid, "count": count, "total": total, "exc": str(e)
            }
            return ret

        if not outputs:
            if job:
                restart_kernels()

            ret["result"] = {
                "status": "ERROR: NO OUTPUTS", "cid": cid, "count": count, "total": total
            }
            return ret

        for idx, output in outputs.items():
            cells[idx]["outputs"] = output

        doc = _set_doc(cells)

        ret = _update_doc_notebook(doc, document, job, cid, count, total)
        if ret:
            return ret

        count += 1

    if total and job:
        restart_kernels()

    ret["result"] = {"status": "COMPLETED", "count": count, "total": total}
    return ret

def _update_doc_notebook(doc, document, job, cid, count, total):
    ret = None
    try:
        nb = Notebooks(**doc).save()
        document.update(notebook=nb, needs_build=False)
    except Exception as e:
        if job:
            restart_kernels()

        ret["result"] = {
            "status": "ERROR", "cid": cid, "count": count, "total": total, "exc": str(e)
        }
        return ret


def _set_doc(cells):
    doc = nbf.new_notebook()
    doc["cells"] = [
        nbf.new_code_cell("from mpcontribs.client import Client"),
        nbf.new_code_cell(f'client = Client()'),
    ]
    doc["cells"] += cells[1:]  # skip localhost Client

    return doc

def _handle_document_notebook(document):
    if document.notebook:
        try:
            nb = Notebooks.objects.get(id=document.notebook.id)
            nb.delete()
            document.update(unset__notebook="")
            logger.debug(f"Notebook {document.notebook.id} deleted.")
        except DoesNotExist:
            pass

def _handle_document_attachmentss(document, cells):
    if document.attachments:
        cells.append(nbf.new_markdown_cell("## Attachments"))
        for attachment in document.attachments:
            cells.append(
                    nbf.new_code_cell("\n".join([
                        f'a = client.get_attachment("{attachment.id}")',
                        'a.info()'
                    ]))
                )

def _handle_document_structures(document, cells):
    if document.structures:
        cells.append(nbf.new_markdown_cell("## Structures"))
        for structure in document.structures:
            cells.append(
                    nbf.new_code_cell("\n".join([
                        f's = client.get_structure("{structure.id}")',
                        's.display()'
                    ]))
                )

def _handle_document_tables(document, cells):
    if document.tables:
        cells.append(nbf.new_markdown_cell("## Tables"))
        for table in document.tables:
            cells.append(
                    nbf.new_code_cell("\n".join([
                        f't = client.get_table("{table.id}")',
                        't.display()'
                    ]))
                )

def _build_query(projects, cids, force):
    query = Q()

    if projects:
        query &= Q(project__in=projects)
    if cids:
        query &= Q(id__in=cids)
    if not force:
        query &= Q(needs_build=True) | Q(needs_build__exists=False)
    return query
