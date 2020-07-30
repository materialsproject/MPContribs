# -*- coding: utf-8 -*-
import asyncio
import requests
from uuid import uuid4
from tornado.escape import json_encode, json_decode, url_escape
from websocket import create_connection
from notebook.utils import url_path_join
from notebook.gateway.managers import GatewayClient


def run_cells(kernel_id, cid, cells):
    gw_client = GatewayClient.instance()
    url = url_path_join(
        gw_client.ws_url, gw_client.kernels_endpoint, url_escape(kernel_id), "channels",
    )
    outputs = {}
    ws = create_connection(url)

    for idx, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            ws.send(
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
                            "code": cell["source"],
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

            outputs[idx] = []
            status = None
            while status is None or status == "busy":
                msg = ws.recv()
                msg = json_decode(msg)
                msg_type = msg["msg_type"]
                if msg_type == "status":
                    status = msg["content"]["execution_state"]
                elif msg_type in ["stream", "display_data", "execute_result"]:
                    # display_data/execute_result required fields:
                    #   "output_type", "data", "metadata"
                    # stream required fields: "output_type", "name", "text"
                    output = msg["content"]
                    output.pop("transient", None)
                    output["output_type"] = msg_type
                    outputs[idx].append(output)

    ws.close()
    return outputs


async def execute_cells(cid, cells, loop=None):
    gw_client = GatewayClient.instance()
    base_endpoint = url_path_join(gw_client.url, gw_client.kernels_endpoint)
    response = await loop.run_in_executor(None, requests.get, base_endpoint)
    kernels = response.json()

    while 1:
        for kernel in kernels:
            if kernel["execution_state"] == "idle":
                kernel_id = kernel["id"]
                print(f"{kernel_id} AVAILABLE")
                return await loop.run_in_executor(
                    None, run_cells, kernel_id, cid, cells
                )
        else:
            print("WAITING for kernel")
            await asyncio.sleep(5, loop=loop)
