#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

python manage.py migrate --noinput
exec wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 60 -- ddtrace-run gunicorn \
    -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS --statsd-host $DD_AGENT_HOST:8125 \
    --access-logfile - --error-logfile - --log-level $DD_LOG_LEVEL $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    --name $SUPERVISOR_PROCESS_NAME wsgi
