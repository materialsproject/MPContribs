# TODO ddtrace
import os
import json
import logging
import boto3

from pathlib import Path
from shutil import make_archive, rmtree
from mpcontribs.client import Client

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    logger.info(f"Received event: {event}")
    query, include = event["query"], event["include"]
    project, fmt = query["project"], query["format"]
    filename = event["filename"]
    key = f"{filename}_{fmt}.zip"

    try:
        client = Client(
            host=event["host"], headers=event["headers"], project=project
        )
        logger.info(client.get_totals())
        remaining = context.get_remaining_time_in_millis() / 1000. - 0.5
        logger.debug(f"REMAINING {remaining:.1f}s")
        all_ids = client.get_all_ids(
            query=query, include=include, timeout=remaining/2.
        ).get(project)
        logger.info(f"ALL_IDS {len(all_ids)}")
        tmpdir = Path("/tmp")
        outdir = tmpdir / filename
        remaining = context.get_remaining_time_in_millis() / 1000. - 0.5
        logger.debug(f"REMAINING {remaining:.1f}s")
        ndownloads = client.download_contributions(
            query=query, include=include, outdir=outdir, timeout=remaining
        )
        logger.info(f"DOWNLOADS: {ndownloads}")
        make_archive(outdir, "zip", outdir)
        zipfile = outdir.with_suffix(".zip")
        resp = zipfile.read_bytes()
        s3_client.put_object(
            Bucket=event["bucket"], Key=key,
            Body=resp, ContentType="application/zip"
        )
        rmtree(outdir)
        os.remove(zipfile)
        logger.info("DONE")
    except Exception as e:
        logger.error(f"Exception: {e}", exc_info=True)
