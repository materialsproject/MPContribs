#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -q -t 50 -- ddtrace-run gunicorn "mpcontribs.api:create_app()"
