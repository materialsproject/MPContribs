#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

exec wait-for-it.sh $JUPYTER_GATEWAY_HOST -t 50 -- gunicorn -c gunicorn.conf.py \
    -b 0.0.0.0:$API_PORT -k gevent -w $NWORKERS \
    --access-logfile - --error-logfile - --log-level $FLASK_LOG_LEVEL $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    "mpcontribs.api:create_app()"
