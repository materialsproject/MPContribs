# -*- coding: utf-8 -*-
from uuid import uuid1
from flask import current_app
from tornado.escape import json_encode, json_decode


def run_cells(kernel_id, cid, cells):
    print(f"running {cid} on {kernel_id}")
    ws = current_app.kernels[kernel_id]["ws"]
    ws.ping()
    outputs = {}

    for idx, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            ws.send(
                json_encode(
                    {
                        "header": {
                            "username": cid,
                            "version": "5.3",
                            "session": "",
                            "msg_id": f"{cid}-{idx}-{uuid1()}",
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
                        "buffers": [],
                    }
                )
            )

            outputs[idx] = []
            status = None
            while status is None or status == "busy" or not len(outputs[idx]):
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
                    msg_idx = msg["parent_header"]["msg_id"].split("-")[1]
                    outputs[int(msg_idx)].append(output)
                elif msg_type == "error":
                    tb = msg["content"]["traceback"]
                    raise ValueError(tb)

    return outputs
