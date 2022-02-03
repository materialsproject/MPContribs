#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -t 50 -- ddtrace-run gunicorn \
    -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS --statsd-host $DD_AGENT_HOST:8125 \
    --access-logfile - --error-logfile - --log-level $FLASK_LOG_LEVEL $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    --name $SUPERVISOR_PROCESS_NAME "mpcontribs.api:create_app()"
