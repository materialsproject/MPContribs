# -*- coding: utf-8 -*-
import os
import asyncio
import dateparser
import flask_mongorest

from flask_sse import sse
from flask import Blueprint, request
from flask_mongorest.methods import Fetch
from flask_mongorest import operators as ops
from flask_mongorest.resources import Resource

from uuid import uuid4
from copy import deepcopy
from nbformat import v4 as nbf
from notebook.utils import run_sync, url_path_join
from mongoengine import DoesNotExist
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
from notebook.gateway.managers import GatewayKernelManager, GatewayClient
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
from tornado.escape import json_encode, json_decode, url_escape

from mpcontribs.api.core import SwaggerView
from mpcontribs.api.tables.document import Tables
from mpcontribs.api.notebooks.document import Notebooks
from mpcontribs.api.structures.document import Structures


asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
templates = os.path.join(os.path.dirname(flask_mongorest.__file__), "templates")
notebooks = Blueprint("notebooks", __name__, template_folder=templates)
manager = GatewayKernelManager()
seed_nb = nbf.new_notebook()
seed_nb["cells"] = [nbf.new_code_cell("from mpcontribs.client import Client")]


def connect_kernel():
    # TODO check status busy/idle
    run_sync(manager.list_kernels())
    kernels = {
        kernel_id: dateparser.parse(kernel["last_activity"])
        for kernel_id, kernel in manager._kernels.items()
    }
    kernel_id = url_escape(sorted(kernels, key=kernels.get)[0])
    client = GatewayClient.instance()
    url = url_path_join(client.ws_url, client.kernels_endpoint, kernel_id, "channels")
    ws_req = HTTPRequest(url=url)
    return run_sync(websocket_connect(ws_req))


def execute(ws, cid, code):
    ws.write_message(
        json_encode(
            {
                "header": {
                    "username": cid,
                    "version": "5.3",
                    "session": "",
                    "msg_id": uuid4().hex,
                    "msg_type": "execute_request",
                },
                "parent_header": {},
                "channel": "shell",
                "content": {
                    "code": code,
                    "silent": False,
                    "store_history": False,
                    "user_expressions": {},
                    "allow_stdin": False,
                    "stop_on_error": True,
                },
                "metadata": {},
                "buffers": {},
            }
        )
    )

    outputs, status = [], None
    while status is None or status == "busy":
        msg = run_sync(ws.read_message())
        msg = json_decode(msg)
        msg_type = msg["msg_type"]
        if msg_type == "status":
            status = msg["content"]["execution_state"]
        elif msg_type in ["stream", "display_data", "execute_result"]:
            # display_data/execute_result required fields: "output_type", "data", "metadata"
            # stream required fields: "output_type", "name", "text"
            output = msg["content"]
            output.pop("transient", None)
            output["output_type"] = msg_type
            outputs.append(output)

    return outputs


class NotebooksResource(Resource):
    document = Notebooks
    filters = {"is_public": [ops.Boolean]}
    fields = ["is_public", "nbformat", "nbformat_minor", "metadata", "cells"]


class NotebooksView(SwaggerView):
    resource = NotebooksResource
    methods = [Fetch]

    def get(self, **kwargs):
        cid = kwargs["pk"]
        qfilter = lambda qs: self.has_read_permission(request, qs.clone())
        try:
            # trigger DoesNotExist if necessary (due to permissions or non-existence)
            nb = self._resource.get_object(cid, qfilter=qfilter)
            try:
                if not nb.cells[-1]["outputs"]:
                    ws = connect_kernel()
                    for idx, cell in enumerate(nb.cells):
                        if cell["cell_type"] == "code":
                            cell["outputs"] = execute(ws, cid, cell["source"])
                            sse.publish(
                                {"message": idx + 1}, type="notebook", channel=cid
                            )

                    ws.close()
                    nb.cells[1] = nbf.new_code_cell(
                        "client = Client('<your-api-key-here>')"
                    )
                    nb.save()  # calls Notebooks.clean()
                    sse.publish({"message": 0}, type="notebook", channel=cid)
            except Exception as ex:
                print(ex)
                sse.publish({"message": -1}, type="notebook", channel=cid)

            return self._resource.serialize(nb, params=request.args)

        except DoesNotExist:
            nb = None
            try:
                nb = Notebooks.objects.only("pk").get(pk=cid)
            except DoesNotExist:
                # create and save unexecuted notebook, also start entry to avoid rebuild on subsequent requests
                from mpcontribs.api.contributions.views import ContributionsResource

                res = ContributionsResource()
                res._params = {"_fields": "_all"}
                contrib = res.get_object(cid, qfilter=qfilter)
                cells = [
                    nbf.new_code_cell(
                        'client = Client(headers={"X-Consumer-Groups": "admin"})'
                    ),
                    nbf.new_markdown_cell("## Project"),
                    nbf.new_code_cell(
                        f'client.get_project("{contrib.project.pk}").pretty()'
                    ),
                    nbf.new_markdown_cell("## Contribution"),
                    nbf.new_code_cell(f'client.get_contribution("{cid}").pretty()'),
                ]

                if contrib.tables:
                    cells.append(nbf.new_markdown_cell("## Tables"))
                    for _, tables in contrib.tables.items():
                        for table in tables:
                            tid = table["id"]
                            cells.append(
                                nbf.new_code_cell(f'client.get_table("{tid}").plot()')
                            )

                if contrib.structures:
                    cells.append(nbf.new_markdown_cell("## Structures"))
                    for _, structures in contrib.structures.items():
                        for structure in structures:
                            sid = structure["id"]
                            cells.append(
                                nbf.new_code_cell(f'client.get_structure("{sid}")')
                            )

                nb = Notebooks(pk=cid, is_public=contrib.is_public)
                doc = deepcopy(seed_nb)
                doc["cells"] += cells
                self.Schema().update(nb, doc)
                nb.save()  # calls Notebooks.clean()
                return self._resource.serialize(nb, params=request.args)

            if nb is not None:
                raise DoesNotExist(
                    f"Notebook {nb.id} exists but user not in project group"
                )
