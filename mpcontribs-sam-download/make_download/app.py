# TODO ddtrace
import os
import json
import logging
import boto3

from redis import Redis
from pathlib import Path
from shutil import make_archive, rmtree
from mpcontribs.client import Client

logger = logging.getLogger()
logger.setLevel(os.environ["MPCONTRIBS_CLIENT_LOG_LEVEL"])
s3_client = boto3.client('s3')
timeout = int(os.environ["LAMBDA_TIMEOUT"])
redis_address = os.environ["REDIS_ADDRESS"]
store = Redis.from_url(f"redis://{redis_address}")
store.ping()

def get_remaining(event, context):
    remaining = context.get_remaining_time_in_millis() / 1000. - 0.5
    if remaining < 3:
        raise ValueError("TIMEOUT in 3s!")

    elapsed_pct = (timeout - remaining) / timeout * 100.
    store.set(event["redis_key"], f"{elapsed_pct:.1f}")
    return remaining


def lambda_handler(event, context):
    get_remaining(event, context)
    query, include = event["query"], event["include"]
    project = query["project"]
    bucket, filename, fmt, version = event["redis_key"].split(":")

    try:
        client = Client(
            host=event["host"], headers=event["headers"], project=project
        )
        remaining = get_remaining(event, context)
        tmpdir = Path("/tmp")
        outdir = tmpdir / filename
        ndownloads = client.download_contributions(
            query=query, include=include, outdir=outdir, timeout=remaining
        )
        get_remaining(event, context)
        make_archive(outdir, "zip", outdir)
        get_remaining(event, context)
        zipfile = outdir.with_suffix(".zip")
        resp = zipfile.read_bytes()
        s3_client.put_object(
            Bucket=bucket, Key=f"{filename}_{fmt}.zip",
            Metadata={"version": version},
            Body=resp, ContentType="application/zip"
        )
        get_remaining(event, context)
        rmtree(outdir)
        os.remove(zipfile)
        store.set(event["redis_key"], "READY")
    except Exception as e:
        logger.error(str(e), exc_info=True)
        store.set(event["redis_key"], "ERROR")
