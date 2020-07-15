# -*- coding: utf-8 -*-
import asyncio
import dateparser

from uuid import uuid4
from notebook.utils import run_sync, url_path_join

from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
from notebook.gateway.managers import GatewayKernelManager, GatewayClient
from tornado.platform.asyncio import AnyThreadEventLoopPolicy
from tornado.escape import json_encode, json_decode, url_escape

asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())
manager = GatewayKernelManager()


def connect_kernel():
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
