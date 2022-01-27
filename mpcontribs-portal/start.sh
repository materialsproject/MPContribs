#!/bin/bash

zzz=$(($DEPLOYMENT*60))
echo "$SUPERVISOR_PROCESS_NAME: waiting for $zzz seconds before start..."
sleep $zzz

exec python manage.py migrate --noinput
exec wait-for-it.sh $MPCONTRIBS_API_HOST -s -t 60 -- gunicorn -c gunicorn.conf.py \
    -b 0.0.0.0:$PORTAL_PORT -k gevent -w $NWORKERS \
    --access-logfile - --error-logfile - --log-level debug $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    wsgi
