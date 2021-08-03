# -*- coding: utf-8 -*-
import os
import time
import requests
import flask_mongorest

from rq import get_current_job
from rq.job import Job
from rq_scheduler import Scheduler
from time import sleep
from copy import deepcopy
from nbformat import v4 as nbf
from flask_rq2 import RQ
from flask import Blueprint, request, current_app, abort, jsonify
from flask_mongorest import operators as ops
from flask_mongorest.methods import Fetch, BulkFetch
from flask_mongorest.resources import Resource
from mongoengine.context_managers import no_dereference
from mongoengine.errors import DoesNotExist
from mongoengine.queryset.visitor import Q

from mpcontribs.api import get_kernel_endpoint
from mpcontribs.api.config import API_CNAME, QUEUE_NAME, CRON_JOB_ID
from mpcontribs.api.core import SwaggerView
from mpcontribs.api.projects.document import Projects
from mpcontribs.api.contributions.document import Contributions
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.notebooks import run_cells

templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)

MPCONTRIBS_API_HOST = os.environ.get("MPCONTRIBS_API_HOST", "localhost:5000")
seed_nb = nbf.new_notebook()
seed_nb["cells"] = [
    nbf.new_code_cell("from mpcontribs.client import Client"),
    nbf.new_code_cell(f'client = Client(host="{API_CNAME}")'),
]

rq = RQ()


class NotebooksScheduler(Scheduler):
    redis_scheduler_namespace_prefix = f'rq:scheduler_instance:{API_CNAME}:'
    scheduler_key = f'rq:scheduler:{API_CNAME}'
    scheduler_lock_key = f'rq:scheduler_lock:{API_CNAME}'
    scheduled_jobs_key = f'rq:scheduler:scheduled_jobs:{API_CNAME}'


class NotebooksResource(Resource):
    document = Notebooks
    filters = {"id": [ops.In, ops.Exact]}
    fields = ["id", "nbformat", "nbformat_minor"]
    allowed_ordering = ["name"]
    paginate = True
    default_limit = 10
    max_limit = 100

    @staticmethod
    def get_optional_fields():
        return ["nbformat", "nbformat_minor", "metadata", "cells"]


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
                print(f"{kernel_id} busy with {running_cid}")
        else:
            print("WAITING for a kernel to become available")
            sleep(5)
            ntries += 1


@notebooks.route("/build")
def build():
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
    kernel_ids = [k for k, v in current_app.kernels.items() if v["cid"] is None]

    for kernel_id in kernel_ids:
        kernel_url = get_kernel_endpoint(kernel_id) + "/restart"
        r = requests.post(kernel_url, json={})
        cells = [nbf.new_code_cell("\n".join([
            "from mpcontribs.client import Client",
            "print('client imported')"
        ]))]
        run_cells(kernel_id, "import-client", cells)


@notebooks.route('/result', defaults={'job_id': f"cron-{CRON_JOB_ID}"})
@notebooks.route("/result/<job_id>")
def result(job_id):
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


@rq.job(QUEUE_NAME)
def make(projects=None, cids=None, force=False):
    """build the notebook / details page"""
    start = time.perf_counter()
    remaining_time = rq.default_timeout - 5
    mask = ["id", "needs_build", "notebook"]
    query = Q()

    if projects:
        query &= Q(project__in=projects)
    if cids:
        query &= Q(id__in=cids)
    if not force:
        query &= Q(needs_build=True) | Q(needs_build__exists=False)

    job = get_current_job()
    ret = {"input": {"projects": projects, "cids": cids, "force": force}}
    if job:
        ret["job"] = {
            "id": job.id,
            "enqueued_at": job.enqueued_at.isoformat(),
            "started_at": job.started_at.isoformat()
        }

    with no_dereference(Contributions) as Contribs:
        documents = Contribs.objects(query).only(*mask)
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

            if document.notebook:
                try:
                    nb = Notebooks.objects.get(id=document.notebook.id)
                    nb.delete()
                    document.update(unset__notebook="")
                    print(f"Notebook {document.notebook.id} deleted.")
                except DoesNotExist:
                    pass

            cid = str(document.id)
            print(f"prep notebook for {cid} ...")
            document.reload("tables", "structures", "attachments")

            cells = [
                # define client only once in kernel
                # avoids API calls for regex expansion for query parameters
                nbf.new_code_cell("\n".join([
                    "if 'client' not in locals():",
                    "\tclient = Client(",
                    '\t\theaders={"X-Authenticated-Groups": "admin"},',
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

            if document.tables:
                cells.append(nbf.new_markdown_cell("## Tables"))
                for table in document.tables:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f't = client.get_table("{table.id}")',
                            't.display()'
                        ]))
                    )

            if document.structures:
                cells.append(nbf.new_markdown_cell("## Structures"))
                for structure in document.structures:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f's = client.get_structure("{structure.id}")',
                            's.display()'
                        ]))
                    )

            if document.attachments:
                cells.append(nbf.new_markdown_cell("## Attachments"))
                for attachment in document.attachments:
                    cells.append(
                        nbf.new_code_cell("\n".join([
                            f'a = client.get_attachment("{attachment.id}")',
                            'a.info()'
                        ]))
                    )

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

            doc = deepcopy(seed_nb)
            doc["cells"] += cells[1:]  # skip localhost Client

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

            count += 1

        if job:
            restart_kernels()

        ret["result"] = {"status": "COMPLETED", "count": count, "total": total}

    return ret
