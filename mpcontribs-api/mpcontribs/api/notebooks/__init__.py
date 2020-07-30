# -*- coding: utf-8 -*-
import asyncio
from uuid import uuid4
from notebook.utils import url_path_join
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
from notebook.gateway.managers import GatewayKernelManager, GatewayClient
from tornado.escape import json_encode, json_decode, url_escape
from websocket import create_connection
from notebook.utils import url_path_join
from notebook.gateway.managers import GatewayClient


async def execute_cells(cid, cells, loop=None):
    manager = GatewayKernelManager()
    manager.loop = loop
    ws = None

    while ws is None:
        await manager.list_kernels()
        for kernel_id, kernel in manager._kernels.items():
            if kernel["execution_state"] == "idle":
                print(f"kernel {kernel_id} is available.")
                client = GatewayClient.instance()
                url = url_path_join(
                    client.ws_url,
                    client.kernels_endpoint,
                    url_escape(kernel_id),
                    "channels",
                )
                ws_req = HTTPRequest(url=url)
                ws = await websocket_connect(ws_req)

        print("waiting for kernel to become available...")
        await asyncio.sleep(5, loop=loop)

    outputs = {}
    for idx, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            print(cid, idx)
            outputs[idx] = await asyncio.sleep(1, loop=loop)

            await ws.write_message(
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
                msg = await ws.read_message()
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
                    outputs[idx].append(output)

    ws.close()  #  TODO await?
    return outputs
