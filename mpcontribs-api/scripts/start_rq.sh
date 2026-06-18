#!/bin/bash
#
# RQ worker placeholder.
#
# The FastAPI rewrite has not yet ported the background worker (the old worker ran
# `flask rq worker`, and Flask is gone). This stub exists so supervisord's `*-worker`
# programs — referenced by supervisord.conf.jinja and started by main.py's `start("rq:*")`
# — have a command to run and do not crash-loop or enter FATAL.
#
# It honors the same startup stagger as the api process, then blocks so supervisord sees a
# healthy RUNNING process. Replace the `exec sleep infinity` below with the real worker
# entrypoint once background processing is reimplemented.

set -e
zzz=$((DEPLOYMENT * 60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep "$zzz"

echo "$SUPERVISOR_PROCESS_NAME: RQ worker not yet ported to the FastAPI rewrite; idling."
exec sleep infinity
