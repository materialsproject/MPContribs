#!/usr/bin/env python
import os
import requests
import boto3

from supervisor.options import ClientOptions
from supervisor.supervisorctl import Controller

client = boto3.client('ecs')

def start(program):
    args = ["start", program]
    options = ClientOptions()
    options.realize(args)
    c = Controller(options)
    c.onecmd(" ".join(options.args))

start("api")

metadata_uri = os.environ.get("METADATA_URI", "")
start_rq = True

if metadata_uri:
    # in AWS Fargate with potentially multiple tasks
    print("METADATA URI", metadata_uri)
    r = requests.get(metadata_uri)
    labels = r.json()["Labels"]
    prefix = "com.amazonaws.ecs"
    cluster = labels[f"{prefix}.cluster"].split("/", 1)[1]
    family = labels[f"{prefix}.task-definition-family"]
    version = labels[f"{prefix}.task-definition-version"]
    tasks = client.list_tasks(cluster=cluster, family=family).get("taskArns", [])
    print("TASKS", tasks)
    # TODO check version of each task
    start_rq = len(tasks) == 1  # this task included in metadata response

if start_rq:
    for program in ["worker", "scheduler"]:
        start(program)
